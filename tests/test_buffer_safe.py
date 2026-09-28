"""A lone surrogate never reaches the buffer (it made every later read fail)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plat.util import buffer_safe  # noqa: E402


class BufferSafeTest(unittest.TestCase):
    def test_lone_surrogates_become_one_replacement_each(self):
        s = "ok \udcb3 and \ud83d half, whole 🚀"
        out = buffer_safe(s)
        self.assertEqual(out, "ok � and � half, whole 🚀")
        self.assertEqual(len(out), len(s))       # offsets still line up
        out.encode("utf-8")

    def test_clean_text_is_returned_as_is(self):
        s = "表 🚀 plain"
        self.assertIs(buffer_safe(s), s)

    def test_the_sheet_writes_safe_text(self):
        from ui.sheet import OutputSheet

        class _View(object):
            def __init__(self):
                self.cmds = []

            def is_valid(self):
                return True

            def set_read_only(self, flag):
                pass

            def size(self):
                return 0

            def run_command(self, name, args=None):
                self.cmds.append((name, args))

        sheet = OutputSheet.__new__(OutputSheet)
        sheet.view = _View()
        sheet._has_view = lambda: True
        sheet.finish_buffer_edit = lambda: None
        sheet.write("a\udcb3b")
        sheet.replace(0, 1, "\ud83d")
        texts = [a["text"] for _n, a in sheet.view.cmds]
        self.assertEqual(texts, ["a�b", "�"])


if __name__ == "__main__":
    unittest.main()
