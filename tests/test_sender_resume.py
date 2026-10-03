"""A send_to_session message on a resumed sheet shows as `📬 from …`, and the
routing header no longer carries the sender's whole auto-name (its task)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.registry import stamp_sender_prompt  # noqa: E402
from features.resume import display_prompt  # noqa: E402

NAME = ("https://github.com/Gaxil/Unity-InteriorMapping <- port this to pil's "
        "render package, do build interactive demo entry")


class SenderOnResumeTest(unittest.TestCase):
    def _stamped(self):
        return stamp_sender_prompt(
            "Codex review of render.rain_glass. IMPLEMENT these findings.",
            sender_agent_id="submarine::2dfaeabaabdd",
            sender_session_id="01a0f88f-d0cc-7a40-87ed-2c8412307768",
            sender_name=NAME)

    def test_the_header_clips_a_long_sender_name(self):
        head = self._stamped().split("\n", 1)[0]
        self.assertNotIn("demo entry", head)
        self.assertIn("name=https://github.com/Gaxil", head)
        self.assertTrue(head.endswith("…"))

    def test_a_resumed_message_shows_its_mail_label(self):
        raw = "<user_query>\n%s\n</user_query>" % self._stamped()
        shown = display_prompt(raw)
        self.assertTrue(shown.startswith("📬 from https://github.com/Gaxil"), shown)
        self.assertIn("Codex review of render.rain_glass", shown)
        self.assertNotIn("[from agent", shown)

    def test_plain_user_text_is_unchanged(self):
        self.assertEqual(display_prompt("<user_query>\nhello\n</user_query>"), "hello")
        self.assertEqual(display_prompt("hello"), "hello")


if __name__ == "__main__":
    unittest.main()
