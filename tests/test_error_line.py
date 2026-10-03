"""Errors print as `⚠ @error(…)`, in the @done form, and the syntax paints them red."""
import os
import re
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.turn import format_error_line  # noqa: E402


class ErrorLineTest(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(format_error_line("Failed to connect: boom."),
                         "\n  ⚠ @error(Failed to connect: boom)\n")

    def test_whitespace_collapses_to_one_line(self):
        self.assertEqual(format_error_line("a\n  b\tc"), "\n  ⚠ @error(a b c)\n")
        self.assertEqual(format_error_line(""), "\n  ⚠ @error(error)\n")

    def test_the_syntax_scopes_it_as_an_error(self):
        with open(os.path.join(_ROOT, "SubmarineOutput.sublime-syntax"),
                  encoding="utf-8") as f:
            src = f.read()
        rules = re.findall(r"match: '\^\\s\*⚠ @error[^']*'\n\s+scope: (\S+)", src)
        self.assertEqual(rules, ["submarine.tool.error", "submarine.tool.error"])


if __name__ == "__main__":
    unittest.main()


class BackgroundRowAfterDoneTest(unittest.TestCase):
    """A ⚙ row under a turn's @done (a background task still running) is
    styled: @done ends the turn's context, where the ⚙ rule lived."""

    def test_the_top_level_styles_an_indented_background_row(self):
        import yaml
        with open(os.path.join(_ROOT, "SubmarineOutput.sublime-syntax"),
                  encoding="utf-8") as f:
            main = yaml.safe_load(f)["contexts"]["main"]
        rules = [(r.get("match"), r.get("scope")) for r in main if isinstance(r, dict)]
        self.assertIn((r"^\s+⚙ .+$", "submarine.tool.background"), rules)
        line = "  ⚙ Agent: Explore — Mesh assets (background)"
        self.assertTrue(re.match(r"^\s+⚙ .+$", line))
        self.assertFalse(re.match(r"^\s+⚙ .+$", "⚙ Background task finished ▷"))
