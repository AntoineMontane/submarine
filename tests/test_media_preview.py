"""Inline image preview under media tool lines (sublime-claude port)."""
from __future__ import annotations

import os
import tempfile
import unittest

from ui.renderer import TurnRenderer


# 1×1 red PNG
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)


class _Owner(object):
    view = None


class TestMediaPreview(unittest.TestCase):
    def setUp(self):
        self.r = TurnRenderer(_Owner())
        fd, self.path = tempfile.mkstemp(suffix=".png")
        os.write(fd, _PNG)
        os.close(fd)

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def test_png_header_size(self):
        self.assertEqual(self.r._image_dimensions_from_bytes(_PNG), (1, 1))

    def test_phantom_html_embeds_data_uri(self):
        html = self.r._media_phantom_html(self.path, "images/1.png")
        self.assertIn("<img src=\"data:image/", html)
        self.assertIn("width=", html)
        self.assertIn("height=", html)
        self.assertIn("enlarge", html)
        self.assertNotIn("🖼", html)


if __name__ == "__main__":
    unittest.main()


class ClaudeReadImageTest(unittest.TestCase):
    """Claude reads images with plain Read: same phantom as ACP media tools."""

    def _tool(self, path, name="Read"):
        from ui.models import ToolCall
        t = ToolCall(name=name, tool_input={"file_path": path})
        t.status = "done"
        t.result = "[image]"
        return t

    def test_read_of_an_image_is_media(self):
        from ui.formatters import is_media_tool
        self.assertTrue(is_media_tool(self._tool("/tmp/eb_game_prev.png")))
        self.assertFalse(is_media_tool(self._tool("/tmp/notes.md")))
        self.assertTrue(is_media_tool(self._tool("/tmp/x.txt", name="read_image")))

    def test_the_row_says_image_not_lines(self):
        from ui.formatters import _read

        class _V(object):
            def _format_read_result(self, result):
                return " → 1 lines"
        self.assertEqual(_read(_V(), self._tool("/tmp/eb_game_prev.png")),
                         ": /tmp/eb_game_prev.png → image")
