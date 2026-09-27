"""resolve_init_model chain; new session ignores leftover view stamp."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BRIDGE = os.path.join(_ROOT, "bridge")
for p in (_ROOT, _BRIDGE):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.registry import resolve_init_model, resolve_spawn_model


class TestResolveInitModel(unittest.TestCase):
    def setUp(self):
        self.resolve = resolve_init_model

    def test_new_session_uses_default(self):
        self.assertEqual(
            self.resolve(default_model="grok-4.6"),
            "grok-4.6",
        )

    def test_profile_beats_default(self):
        self.assertEqual(
            self.resolve(
                profile_model="deepseek-v4-pro",
                default_model="grok-4.6",
            ),
            "deepseek-v4-pro",
        )

    def test_requested_beats_profile(self):
        self.assertEqual(
            self.resolve(
                requested_model="deepseek-v4-flash-vision-exp",
                profile_model="deepseek-v4-pro",
                default_model="grok-4.6",
            ),
            "deepseek-v4-flash-vision-exp",
        )

    def test_spawn_fork_inherits_source_model(self):
        self.assertEqual(
            resolve_spawn_model(
                source_model="deepseek-v4-flash",
                forking=True,
            ),
            "deepseek-v4-flash",
        )
        self.assertEqual(
            resolve_spawn_model(
                requested="deepseek-v4-pro",
                source_model="deepseek-v4-flash",
                forking=True,
            ),
            "deepseek-v4-pro",
        )
        self.assertIsNone(
            resolve_spawn_model(
                source_model="deepseek-v4-flash",
                forking=False,
            ),
        )

    def test_live_session_beats_default(self):
        self.assertEqual(
            self.resolve(
                session_model="deepseek-v4-flash",
                default_model="grok-4.6",
            ),
            "deepseek-v4-flash",
        )

    def test_new_session_ignores_view_stamp(self):
        self.assertEqual(
            self.resolve(
                view_model="deepseek-v4-pro",
                default_model="grok-4.6",
            ),
            "grok-4.6",
        )

    def test_resume_view_stamp_beats_default(self):
        self.assertEqual(
            self.resolve(
                view_model="deepseek-v4-pro",
                default_model="grok-4.6",
                resume=True,
            ),
            "deepseek-v4-pro",
        )

    def test_saved_beats_default(self):
        self.assertEqual(
            self.resolve(
                saved_model="deepseek-v4-pro",
                default_model="grok-4.6",
            ),
            "deepseek-v4-pro",
        )

    def test_resume_uses_default_if_nothing_saved(self):
        self.assertEqual(
            self.resolve(default_model="grok-4.6", resume=True),
            "grok-4.6",
        )

    def test_resume_keeps_saved_deepseek(self):
        self.assertEqual(
            self.resolve(
                saved_model="deepseek-v4-pro",
                default_model="grok-4.6",
                resume=True,
            ),
            "deepseek-v4-pro",
        )

    def test_profile_beats_live_and_saved(self):
        self.assertEqual(
            self.resolve(
                profile_model="deepseek-v4-flash",
                session_model="grok-4.6",
                saved_model="grok-4.6",
                default_model="grok-4.6",
            ),
            "deepseek-v4-flash",
        )

    def test_blank_strings_are_skipped(self):
        self.assertEqual(
            self.resolve(
                session_model="  ",
                view_model="",
                saved_model="deepseek-v4-pro",
                default_model="grok-4.6",
            ),
            "deepseek-v4-pro",
        )


class _ModelBridge:
    """Minimal stand-in for AcpBridge.normalize/resolve_applied_model."""

    def __init__(self):
        from acp_base import AcpBridge
        self.DEFAULT_MODEL = "grok-4.6"
        self.MODEL_ALIASES = dict(AcpBridge.MODEL_ALIASES)
        self.MODEL_ALIASES.update({
            "grok-4.5": "grok-4.6",
            "deepseek-pro": "deepseek-v4-pro",
        })
        self.normalize_model = AcpBridge.normalize_model.__get__(self, _ModelBridge)
        self.resolve_applied_model = AcpBridge.resolve_applied_model.__get__(
            self, _ModelBridge)


class TestResolveAppliedModel(unittest.TestCase):
    def setUp(self):
        self.b = _ModelBridge()

    def test_trusts_agent_current(self):
        self.assertEqual(
            self.b.resolve_applied_model("deepseek-v4-pro", "grok-4.6"),
            "grok-4.6",
        )

    def test_accepts_alias_of_requested(self):
        self.assertEqual(
            self.b.resolve_applied_model("deepseek-pro", "deepseek-v4-pro"),
            "deepseek-v4-pro",
        )

    def test_empty_current_keeps_requested(self):
        self.assertEqual(
            self.b.resolve_applied_model("deepseek-v4-pro", None),
            "deepseek-v4-pro",
        )


class TestClearDispatch(unittest.TestCase):
    def test_acp_exposes_clear(self):
        from acp_base import AcpBridge

        class _B(AcpBridge):
            def __init__(self):
                pass

        table = AcpBridge.extra_dispatch(_B())
        self.assertIn("clear", table)
        self.assertEqual(table["clear"].__name__, "handle_clear")


class TestGrokSpawnModelFlag(unittest.TestCase):
    def test_spawn_passes_session_model(self):
        from grok_main import GrokBridge

        class _Spawn(GrokBridge):
            def __init__(self):
                self.model = "deepseek-v4-pro"
                self.effort = ""
                self.permission_mode = "default"
                self._always_approve = False

        argv = _Spawn().agent_argv()
        self.assertIn("--model", argv)
        self.assertIn("deepseek-v4-pro", argv)


class TestGrokVisionCatalog(unittest.TestCase):
    def test_flash_vision_is_vision(self):
        from backend.grok import (
            GROK_MODELS, model_supports_vision, normalize_grok_model,
        )
        ids = [mid for mid, _label in GROK_MODELS]
        self.assertIn("deepseek-v4-flash-vision-exp", ids)
        self.assertTrue(model_supports_vision("deepseek-v4-flash-vision-exp"))
        self.assertTrue(model_supports_vision("ds-vision"))
        # DeepSeek V4 / V4.1 BYOK advertise read_image (ACP read_file still
        # rejects binary). Pre-v4 DeepSeek stays off — the tool call can
        # hard-fail the turn.
        self.assertTrue(model_supports_vision("deepseek-v4-flash"))
        self.assertTrue(model_supports_vision("deepseek-v4-pro"))
        self.assertTrue(model_supports_vision("ds-flash"))
        self.assertFalse(model_supports_vision("deepseek-chat"))
        self.assertFalse(model_supports_vision("deepseek-reasoner"))
        self.assertEqual(
            normalize_grok_model("ds-flash-vision"),
            "deepseek-v4-flash-vision-exp",
        )


if __name__ == "__main__":
    unittest.main()


class ProviderLineTest(unittest.TestCase):
    def test_the_banner_reads_like_done(self):
        from ui.render_policy import identity_parts
        self.assertEqual(identity_parts("Grok", "grok-4.6", "high"), ["Grok/grok-4.6", "effort:high"])
        self.assertEqual(identity_parts("Claude", "opus", ""), ["opus"])
        import os
        syn = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "SubmarineOutput.sublime-syntax"), encoding="utf-8").read()
        self.assertIn("^\\s*@session\\(.*\\)$", syn)

    """Every sheet says what it runs on, above its history."""

    def test_new_session_shows_provider_model_and_effort(self):
        from tests.fakes import FakeClient, make_session
        s = make_session(client=FakeClient(), backend="grok",
                         settings={"effort": "high"})
        s.start()
        s._on_init({"status": "initialized", "session_id": "y", "model": "grok-4.7"})
        self.assertEqual(s.output.banners, [("Grok", "grok-4.7", "high")])

    def test_a_resumed_session_shows_it_too(self):
        from tests.fakes import FakeClient, make_session
        s = make_session(client=FakeClient(), backend="claude", resume_id="old")
        s.start()
        s._on_init({"status": "initialized", "session_id": "old"})
        self.assertTrue(s.output.banners and s.output.banners[-1][0] == "Claude")

    def test_the_banner_is_on_the_sheet_above_the_history(self):
        """It was output.text() — which drops text while no turn exists, so
        a fresh sheet showed nothing."""
        from tests.stubs import install_sublime
        from tests.test_composer_always_back import _live
        from tests.test_single_view import RecordingWindow
        from ui.host import HostView
        install_sublime()
        win = RecordingWindow()
        s, out, _c = _live(win, "fresh")
        HostView.for_window(win).attach(win, s)
        s._enter_input_with_draft()
        out.set_banner(("Claude", "opus", "high"))
        text = out.view.substr(None)
        self.assertTrue(text.startswith("  @session(opus, effort:high)\n\n"), text)
        self.assertTrue(out.composer.is_input_mode())
        self.assertTrue(text[out.composer._input_start - 2:].startswith("◎ "),
                        "the composer anchor moved with the banner")
        out.prompt("hello")
        out.text("hi there\n")
        out.meta(0)
        out.set_banner(("Claude", "sonnet", "high"))   # replaced, not stacked
        text = out.view.substr(None)
        self.assertEqual(text.count("@session("), 1)
        self.assertTrue(text.startswith("  @session(sonnet, effort:high)"))
        self.assertLess(text.index("@session("), text.index("◎ hello ▶"))
        out.renderer.repaint_from_state()
        text = out.view.substr(None)
        self.assertTrue(text.startswith("  @session(sonnet, effort:high)\n\n◎ hello ▶"), text)


class BannerOverHistoryTest(unittest.TestCase):
    def test_a_banner_added_over_a_live_turn_keeps_its_output_in_place(self):
        from tests.stubs import install_sublime
        from tests.test_composer_always_back import _live
        from tests.test_single_view import RecordingWindow
        from ui.host import HostView
        install_sublime()
        win = RecordingWindow()
        s, out, _c = _live(win, "resumed")
        HostView.for_window(win).attach(win, s)
        out.prompt("earlier question")
        out.text("first part\n")
        out.set_banner(("Kimi Code", "kimi-for-coding", ""))
        out.text("second part\n")
        text = out.view.substr(None)
        self.assertTrue(text.startswith("  @session(Kimi Code/kimi-for-coding)\n\n◎ earlier question ▶"), text)
        self.assertIn("first part\nsecond part", text)
        self.assertEqual(text.count("◎ earlier question"), 1)


class ModelSwitchNoteTest(unittest.TestCase):
    """Picking a model marks the history where it happened."""

    def _sheet(self):
        from tests.stubs import install_sublime
        from tests.test_composer_always_back import _live
        from tests.test_single_view import RecordingWindow
        from ui.host import HostView
        install_sublime()
        win = RecordingWindow()
        s, out, _c = _live(win, "switcher")
        HostView.for_window(win).attach(win, s)
        s.model = "grok-4.7"
        return s, out

    def test_the_switch_is_noted_under_the_last_turn(self):
        s, out = self._sheet()
        out.prompt("hello")
        out.text("hi\n")
        out.meta(0)
        s.note_model_switch("grok-4.7", "grok-4.6")
        text = out.view.substr(None)
        done = text.index("@done")
        note = text.index("  @model(grok-4.7 → grok-4.6)")
        self.assertGreater(note, done)
        out.renderer.repaint_from_state()
        self.assertIn("  @model(grok-4.7 → grok-4.6)", out.view.substr(None))

    def test_the_picker_notes_it(self):
        import commands.provider_cmds as pc
        s, out = self._sheet()
        out.prompt("hello")
        out.meta(0)
        pc._apply_session_model(s, "grok-4.6")
        self.assertIn("@model(grok-4.7 → grok-4.6)", out.view.substr(None))

    def test_before_any_turn_the_banner_says_it(self):
        s, out = self._sheet()
        s.model = "grok-4.6"
        s.note_model_switch("grok-4.7", "grok-4.6")
        text = out.view.substr(None)
        self.assertNotIn("@model(", text)
        self.assertTrue(text.startswith("  @session("), text)
        self.assertIn("grok-4.6", text.split("\n", 1)[0])

    def test_no_note_when_nothing_changed(self):
        s, out = self._sheet()
        out.prompt("hello")
        out.meta(0)
        s.note_model_switch("grok-4.7", "grok-4.7")
        self.assertNotIn("@model(", out.view.substr(None))


class BannerWithContextTest(unittest.TestCase):
    def _check(self, composer_open):
        from tests.stubs import install_sublime
        from tests.test_composer_always_back import _live
        from tests.test_single_view import RecordingWindow
        from ui.host import HostView
        install_sublime()
        win = RecordingWindow()
        s, out, _c = _live(win, "fresh")
        HostView.for_window(win).attach(win, s)
        c = out.composer
        if composer_open:
            s.pending_context = [{"name": "a.py"}]
            s._enter_input_with_draft()
        elif c.is_input_mode():
            c.exit_input_mode(keep_text=False)
        c.set_pending_context([{"name": "a.py"}])       # 📎 before the banner
        out.set_banner(("Claude", "opus", "high"))
        c.set_pending_context([{"name": "a.py"}, {"name": "b.py"}])
        text = out.view.substr(None)
        self.assertTrue(text.startswith("  @session(opus, effort:high)\n\n"), repr(text))
        self.assertEqual(text.count("📎"), 1, repr(text))

    def test_banner_and_context_line_with_the_composer_closed(self):
        """New session with 📎 context: the banner write left the 📎 line's
        region unshifted; its next redraw ate `  @s` and wrote a second 📎."""
        self._check(composer_open=False)

    def test_banner_and_context_line_with_the_composer_open(self):
        self._check(composer_open=True)


class EffortOnResumeTest(unittest.TestCase):
    """Effort is a process option, not transcript state: a woken Claude
    session has to send it again. Opus 5.5 defaults to `medium` (Opus 5 to
    `high`), so a resume that skipped it quietly ran one level lower."""

    def test_a_resumed_claude_session_sends_the_configured_effort(self):
        from tests.fakes import FakeClient, make_session
        s = make_session(client=FakeClient(), backend="claude",
                         resume_id="old", settings={"effort": "high"})
        s.start()
        params = [p for m, p, _cb in s.client.sent if m == "initialize"][0]
        self.assertEqual(params.get("resume"), "old")
        self.assertEqual(params.get("effort"), "high")

    def test_the_opus_alias_is_labelled_opus_5_5(self):
        from backend import specs
        models = dict(specs.BACKENDS["claude"].default_models)
        self.assertEqual(models["opus"], "Opus 5.5")
        self.assertIn("claude-opus-5-5", models)
