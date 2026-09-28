"""Markdown tables: found in assistant text, laid out in pixels for the popup."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.md_table import (  # noqa: E402
    Metrics, find_tables, layout, place_tables, split_row, table_html,
)

DOC = """Intro

| Name | Qty |
|:--|--:|
| apple | 3 |
| 会話 | 12 |

After.
"""


class FindTest(unittest.TestCase):
    def test_a_table_with_its_alignment(self):
        (t,) = find_tables(DOC.split("\n"))
        self.assertEqual(t.header, ["Name", "Qty"])
        self.assertEqual(t.aligns, ["l", "r"])
        self.assertEqual(t.rows, [["apple", "3"], ["会話", "12"]])
        self.assertEqual(t.label, "⊞ table 2×2 …")

    def test_an_open_table_waits_for_the_next_line(self):
        lines = ["| a | b |", "|---|---|", "| 1 | 2 |"]
        self.assertEqual(find_tables(lines), [])
        self.assertEqual(len(find_tables(lines, final=True)), 1)

    def test_fenced_code_is_not_a_table(self):
        lines = ["```", "| a | b |", "|---|---|", "| 1 | 2 |", "```", ""]
        self.assertEqual(find_tables(lines, final=True), [])

    def test_pipes_in_code_and_escaped(self):
        self.assertEqual(split_row("| `a|b` | a \\| b |"), ["`a|b`", "a | b"])


class LayoutTest(unittest.TestCase):
    def test_measured_cjk_widths_size_the_column(self):
        lines = ["| Name | Qty |", "|:--|--:|", "| 会話会話 | 1 |", ""]
        (t,) = find_tables(lines)
        m = Metrics(8.0, {"会": 15.0, "話": 15.0})
        kind, widths, _body = layout(t, 800, m)
        self.assertEqual(kind, "grid")
        self.assertEqual(widths[0], 60.0)          # measured, not 4 × 2 × 8
        self.assertEqual(Metrics(8.0).text("会話会話"), 64.0)   # the estimate

    def test_a_narrow_popup_wraps_then_stacks(self):
        t = find_tables(["| a | b |", "|---|---|",
                         "| " + "word " * 30 + "| " + "text " * 30 + "|", ""])[0]
        m = Metrics(8.0)
        kind, widths, body = layout(t, 400, m)
        self.assertEqual(kind, "grid")
        self.assertGreater(len(body[1][0][0]), 1)          # wrapped lines
        self.assertEqual(layout(t, 60, m)[0], "stacked")

    def test_html_pads_cells_to_the_row_height(self):
        t = find_tables(["| a | b |", "|---|---|",
                         "| x | " + "long " * 40 + "|", ""])[0]
        out = table_html(t, 400, Metrics(8.0))
        self.assertIn("&nbsp;<br>&nbsp;", out)             # short cell padded


class PlaceTest(unittest.TestCase):
    def test_tables_are_found_in_the_buffer_in_order(self):
        content = "◎ prompt ▶\n\n" + DOC + "\n  @done(1s)\n◎ again ▶\n\n" + DOC
        placed = place_tables(content, [(DOC, True, 0), (DOC, True, 0)])
        self.assertEqual(len(placed), 2)
        self.assertTrue(content[placed[0].start:].startswith("| Name | Qty |"))
        self.assertGreater(placed[1].start, placed[0].end)
        self.assertTrue(content[:placed[1].end].endswith("| 会話 | 12 |"))


if __name__ == "__main__":
    unittest.main()
