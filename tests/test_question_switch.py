"""Switching into a sheet that waits on a question must leave it answerable.

The "Other…" input line is view state: `composer.detach()` dropped it when
the sheet went viewless, but the snapshot still painted the `▸ ` line back —
a dead prompt the user could not type into, Enter did nothing, and the
question keys were the only thing left working. The draft now survives the
detach and the line is rebuilt, caret at its end, on re-attach.
"""
from __future__ import annotations

import unittest

import ui.session_list as sl
from tests.stubs import install_sublime
from tests.test_composer_always_back import Q, _live
from tests.test_single_view import RecordingWindow, _SingleViewCase
from ui import keys
from ui.host import HostView


class TestQuestionSurvivesSwitch(_SingleViewCase):
    def setUp(self):
        super().setUp()
        install_sublime()          # commands.* import sublime at module level
        self.win = RecordingWindow()
        self.hv = HostView.for_window(self.win)

    def _switch_back(self, session):
        import commands.session_cmds as sc
        reveal = sc.SubmarineRevealSessionCommand.__new__(sc.SubmarineRevealSessionCommand)
        reveal.window = self.win
        self.assertTrue(reveal._reveal(session, self.win))
        sl.focus_sheet_soon(self.win, session)
        sl.reveal_tail_soon(session)
        session.scheduler.fire_all()

    def test_typing_an_other_answer_survives_a_switch(self):
        a, _ao, _ac = _live(self.win, "front")
        b, bo, _bc = _live(self.win, "asker")
        answered = []
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        b.query("ask")
        bo.question_request(3, Q, lambda ans: answered.append(ans))
        bo.handle_question_key("o")
        bo.view.run_command("append", {"characters": "half typ"})
        self.hv.attach(self.win, a)                    # b goes viewless mid-answer
        a.scheduler.fire_all()
        self._switch_back(b)                           # Ctrl+] / Enter in the list
        view = bo.view
        c = bo.composer
        self.assertTrue(c._question_input_mode, "the ▸ input line is not live again")
        self.assertTrue(keys.read_setting(view.settings(), keys.QUESTION_INPUT_MODE, False))
        self.assertTrue(keys.read_setting(view.settings(), keys.INPUT_MODE, False))
        self.assertEqual(bo.modals.question_input_text(), "half typ")
        self.assertEqual(view.substr(None).count("▸"), 1, "a dead ▸ line was left behind")
        view.run_command("append", {"characters": "ed"})
        self.assertTrue(bo.modals.submit_question_input())
        self.assertEqual(answered, [{"pick": "half typed"}])

    def _lost_flag(self):
        """The state seen live after switches: the answer line and its marker
        are there, the ◎ flag points at it, the question flag is gone."""
        a, _ao, _ac = _live(self.win, "front")
        b, bo, _bc = _live(self.win, "asker")
        answered = []
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        b.query("ask")
        bo.question_request(3, Q, lambda ans: answered.append(ans))
        bo.handle_question_key("o")
        bo.view.run_command("append", {"characters": "my own answer"})
        c = bo.composer
        c._question_input_mode = False
        keys.write_setting(bo.view.settings(), keys.QUESTION_INPUT_MODE, False)
        self.assertTrue(c._input_mode)
        return b, bo, answered

    def test_enter_on_an_answer_line_that_lost_its_flag_still_answers(self):
        b, bo, answered = self._lost_flag()
        self.assertTrue(bo.modals.submit_question_input(),
                        "Enter must answer the question, not send a prompt")
        self.assertEqual(answered, [{"pick": "my own answer"}])
        self.assertEqual(b._queued_prompts, [])

    def test_a_settings_sync_heals_the_lost_flag(self):
        _b, bo, answered = self._lost_flag()
        bo.modals._sync_modal_settings()
        view = bo.view
        self.assertTrue(bo.composer._question_input_mode)
        self.assertTrue(keys.read_setting(view.settings(), keys.QUESTION_INPUT_MODE, False))
        self.assertFalse(keys.read_setting(view.settings(), keys.HAS_QUESTION, True),
                         "the number keys must not grab the typed answer")
        self.assertFalse(view.is_read_only(), "the answer line stays typeable")
        self.assertEqual(bo.modals.question_input_text(), "my own answer")

    def test_a_redrawn_question_drops_busy_glyphs_stranded_below_it(self):
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        b.query("ask")
        bo.question_request(3, Q, lambda ans: None)
        bo.view.run_command("append", {"characters": " ⠼\n ⠼"})
        bo.modals.render_question()
        self.assertTrue(bo.view.substr(None).endswith("[O] Other...\n"),
                        repr(bo.view.substr(None)[-40:]))

    def test_a_stale_output_does_not_tick_into_the_shown_sheet(self):
        a, ao, _ac = _live(self.win, "front")
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, a)
        a._enter_input_with_draft()
        a.query("busy")
        self.hv.attach(self.win, b)                 # a goes viewless
        b._enter_input_with_draft()
        b.query("ask")
        bo.question_request(3, Q, lambda ans: None)
        before = bo.view.substr(None)
        ao.view = bo.view                           # a stale hold on the host
        ao.current.working = True
        for _ in range(3):
            ao.advance_spinner()
        self.assertEqual(bo.view.substr(None), before)

    def test_answering_clears_the_question_stamps(self):
        """A stale `has_question` routed `o` and 1-4 typed in the composer to
        the question keymap, which dropped them; a stale `has_modal` made Esc
        interrupt."""
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        b.query("ask")
        bo.question_request(3, Q, lambda ans: None)
        self.assertTrue(bo.handle_question_key("1"))
        b.scheduler.fire_all()
        st = bo.view.settings()
        self.assertFalse(keys.read_setting(st, keys.HAS_QUESTION, None))
        self.assertFalse(keys.read_setting(st, keys.HAS_MODAL, None))

    def test_a_dropped_modal_restamps_the_sheet(self):
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        b.query("ask")
        bo.question_request(3, Q, lambda ans: None)
        self.assertTrue(keys.read_setting(bo.view.settings(), keys.HAS_QUESTION, None))
        bo.pending_question = None          # any path that drops it
        self.assertFalse(keys.read_setting(bo.view.settings(), keys.HAS_QUESTION, None))

    def _tracking_read_only(self, view):
        ro = {"on": False}                 # the harness view ignores read-only
        view.set_read_only = lambda v: ro.__setitem__("on", bool(v))
        view.is_read_only = lambda: ro["on"]

    def _assert_typeable(self, s, out):
        s.scheduler.fire_all()
        st = out.view.settings()
        self.assertTrue(out.composer.is_input_mode(), "the composer came back")
        self.assertTrue(keys.read_setting(st, keys.INPUT_MODE, False))
        self.assertFalse(keys.read_setting(st, keys.HAS_QUESTION, None))
        self.assertFalse(keys.read_setting(st, keys.HAS_MODAL, None))
        self.assertFalse(out.view.is_read_only(),
                         "typing in the composer must work without a click")

    def test_after_a_permission_the_composer_is_typeable(self):
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        self._tracking_read_only(bo.view)
        b.query("ask")
        bo.modals.permission_request(5, "Bash", {"command": "ls"}, lambda r: None)
        self.assertTrue(bo.view.is_read_only())
        self.assertTrue(bo.modals.handle_permission_key("y"))
        b.turn.end_live()
        self._assert_typeable(b, bo)

    def test_after_a_question_the_composer_is_typeable(self):
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        self._tracking_read_only(bo.view)
        b.query("ask")
        bo.question_request(3, Q, lambda ans: None)
        self.assertTrue(bo.handle_question_key("2"))
        b.turn.end_live()
        self._assert_typeable(b, bo)

    def _two_turns(self):
        from tests.test_single_view import _Region
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        bo.prompt("first")
        bo.text("first answer\n")
        bo.meta(1.0)
        first_end = bo.view.size()
        bo.prompt("second")
        bo.text("I will ask before changing it:\n")
        return b, bo, first_end, _Region

    def test_a_question_goes_under_the_live_turn_not_an_old_one(self):
        """The screenshot: a stale turn region (left on the first turn) put
        the new question under the first turn's @done."""
        b, bo, first_end, _Region = self._two_turns()
        bo.view._regions[keys.CONV_REGION] = [_Region(0, first_end)]   # stale
        bo.question_request(4, Q, lambda ans: None)
        text = bo.view.substr(None)
        self.assertGreater(text.index("❓ pick"), text.index("I will ask before changing it"))
        self.assertEqual(text.count("❓"), 1)

    def test_an_orphaned_question_block_above_is_removed(self):
        b, bo, first_end, _Region = self._two_turns()
        orphan = "\n  ❓ old question\n    [1] x\n"
        at = first_end
        bo.view._content = bo.view._content[:at] + orphan + bo.view._content[at:]
        bo.view._regions[keys.QUESTION_BLOCK] = [_Region(at, at + len(orphan))]
        bo.question_request(4, Q, lambda ans: None)
        text = bo.view.substr(None)
        self.assertNotIn("old question", text)
        self.assertGreater(text.index("❓ pick"), text.index("I will ask before changing it"))

    def test_a_full_clear_keeps_a_pending_question_answerable(self):
        """Cmd+Shift+K dropped the pending question unanswered: the agent
        waited on it forever."""
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        b.query("ask")
        answered = []
        bo.question_request(3, Q, lambda ans: answered.append(ans))
        bo.clear()
        self.assertIsNotNone(bo.pending_question)
        self.assertIn("❓ pick", bo.view.substr(None))
        self.assertTrue(bo.handle_question_key("1"))
        self.assertEqual(answered, [{"pick": "x"}])

    def test_clear_keep_last_keeps_a_pending_question_answerable(self):
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        bo.prompt("older")
        bo.meta(0)
        b._enter_input_with_draft()
        b.query("ask")
        answered = []
        bo.question_request(3, Q, lambda ans: answered.append(ans))
        bo.clear_keep_last()
        self.assertIn("❓ pick", bo.view.substr(None))
        self.assertTrue(bo.handle_question_key("2"))
        self.assertEqual(answered, [{"pick": "y"}])

    def test_output_after_an_idle_clear_is_not_lost(self):
        b, bo, _bc = _live(self.win, "talker")
        self.hv.attach(self.win, b)
        bo.prompt("hello")
        bo.text("hi\n")
        bo.meta(0)
        bo.clear()                              # idle: no turn is kept
        self.assertIsNone(bo.current)
        b.turn.begin_query()                    # the agent works on its own
        self.assertTrue(b.working)
        bo.text("self-wake output\n")
        self.assertIn("self-wake output", bo.view.substr(None))

    def test_output_after_a_clear_mid_turn_keeps_printing(self):
        """The live sheet stopped printing after Cmd+Shift+K: the tracked
        turn region ran past the end of the sheet, the render could not find
        `◎ (continued)` and gave up on every later update."""
        from tests.test_single_view import _Region
        b, bo, _bc = _live(self.win, "talker")
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        b.query("go")
        bo.text("before the clear\n")
        bo.clear()
        self.assertEqual(bo.current.prompt, "(continued)")
        bo.current.events.append("after the clear\n")
        size = bo.view.size()
        bo.view._regions[keys.CONV_REGION] = [_Region(size, size + 4)]   # stale
        bo.renderer._struct_dirty = True
        bo.renderer._render_current()
        text = bo.view.substr(None)
        self.assertIn("after the clear", text)
        self.assertNotIn("before the clear", text)

    def test_a_plain_question_is_still_answerable_after_a_switch(self):
        a, _ao, _ac = _live(self.win, "front")
        b, bo, _bc = _live(self.win, "asker")
        answered = []
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        b.query("ask")
        bo.question_request(3, Q, lambda ans: answered.append(ans))
        self.hv.attach(self.win, a)
        a.scheduler.fire_all()
        self._switch_back(b)
        view = bo.view
        self.assertTrue(keys.read_setting(view.settings(), keys.HAS_QUESTION, False))
        self.assertIn("❓ pick", view.substr(None))
        self.assertNotIn("▸", view.substr(None))
        self.assertTrue(bo.handle_question_key("2"))
        self.assertEqual(answered, [{"pick": "y"}])


if __name__ == "__main__":
    unittest.main()


class _LockingView(object):
    """RecordingView ignores set_read_only; these tests are about the lock."""

    @staticmethod
    def install():
        from tests.test_single_view import RecordingView
        saved = (RecordingView.set_read_only, RecordingView.is_read_only)
        RecordingView.set_read_only = lambda self, v: setattr(self, "_ro", bool(v))
        RecordingView.is_read_only = lambda self: bool(getattr(self, "_ro", False))
        return saved

    @staticmethod
    def remove(saved):
        from tests.test_single_view import RecordingView
        RecordingView.set_read_only, RecordingView.is_read_only = saved


class TestModalSheetStaysLockedAcrossASwitch(_SingleViewCase):
    """A sheet whose tail is a question / plan approval, switched away from
    and back to. Its previous snapshot (taken with the composer open) was
    carried forward: the re-attach turned input mode back on at that
    snapshot's offsets (`input_start` near the top), so the edit guard took
    the whole sheet for the draft and the view was editable end to end —
    and handle_plan_key ignores keys while the composer claims input mode,
    so the plan could not be answered either."""

    def setUp(self):
        super().setUp()
        install_sublime()
        self._saved = _LockingView.install()
        self.win = RecordingWindow()
        self.hv = HostView.for_window(self.win)

    def tearDown(self):
        _LockingView.remove(self._saved)
        super().tearDown()

    def _modal_then_switch(self, open_modal):
        a, ao, _ac = _live(self.win, "front")
        b, bo, _bc = _live(self.win, "asker")
        self.hv.attach(self.win, b)
        b._enter_input_with_draft()
        self.hv.attach(self.win, a)                  # b snapshotted WITH composer
        a._enter_input_with_draft()
        self.hv.attach(self.win, b)
        b.query("ask")
        open_modal(bo)
        self.hv.attach(self.win, a)                  # away …
        a.scheduler.fire_all()
        self.hv.attach(self.win, b)                  # … and back
        b.scheduler.fire_all()
        return b, bo

    def _assert_locked(self, bo):
        view = bo.view
        self.assertFalse(bo.composer._input_mode, "composer flag resurrected under the modal")
        self.assertFalse(keys.read_setting(view.settings(), keys.INPUT_MODE, False))
        self.assertTrue(view.is_read_only(), "the sheet is editable under the modal")

    def test_a_question_sheet_comes_back_locked_and_answerable(self):
        answered = []
        b, bo = self._modal_then_switch(
            lambda o: o.question_request(3, Q, lambda ans: answered.append(ans)))
        self._assert_locked(bo)
        self.assertTrue(bo.handle_question_key("1"))
        self.assertEqual(answered, [{"pick": "x"}])

    def test_a_plan_approval_comes_back_locked_and_answerable(self):
        responses = []
        b, bo = self._modal_then_switch(
            lambda o: o.plan_approval_request(5, "/tmp/plan.md", [], responses.append))
        self._assert_locked(bo)
        self.assertTrue(bo.handle_plan_key("y"), "plan keys ignored after the switch")
        self.assertEqual(len(responses), 1)


class ReadViewlessOutputTest(_SingleViewCase):
    """read_session_output on a session that is not on screen returned
    "Session output view not found"; it reads the sheet from state now."""

    def setUp(self):
        super().setUp()
        install_sublime()
        self.win = RecordingWindow()
        self.hv = HostView.for_window(self.win)

    def test_a_viewless_session_is_read_from_state(self):
        import mcp.socket_server as ss
        a, ao, _ac = _live(self.win, "worker")
        b, bo, _bc = _live(self.win, "front")
        self.hv.attach(self.win, a)
        ao.prompt("map the module")
        ao.text("It has three parts.\n")
        ao.meta(1.0)
        self.hv.attach(self.win, b)            # a goes viewless
        self.assertIsNone(ao.view)
        srv = ss.MCPSocketServer.__new__(ss.MCPSocketServer)
        srv._session_context_budget = lambda s: {}
        res = srv._read_session_output(agent_id=a.agent_id)
        self.assertNotIn("error", res, res)
        self.assertIn("◎ map the module ▶", res["output"])
        self.assertIn("It has three parts.", res["output"])
