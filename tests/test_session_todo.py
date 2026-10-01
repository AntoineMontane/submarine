"""TODO: sessions parked to come back to, listed on top of the Sessions list."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import records  # noqa: E402
from ui import session_list as sl  # noqa: E402


def _row(sid, kind="saved", name=None, **kw):
    r = {"kind": kind, "session_id": sid, "agent_id": "submarine::" + sid,
         "name": name or sid, "backend": "claude", "status": "closed",
         "query_count": 3, "project": "/p"}
    r.update(kw)
    return r


class TodoSectionTest(unittest.TestCase):
    def test_parked_rows_move_to_a_todo_section_on_top(self):
        live = [_row("a", kind="live", status="ready"), _row("b", kind="live", status="ready")]
        here = [_row("c"), _row("d")]
        text, index = sl.render_list(live, here, [], set(), cols=100, todo={"b", "d"})
        order = [l.split(" (")[0] for l in text.splitlines()
                 if l.startswith(("TODO", "CURRENT", "HISTORY"))]
        self.assertEqual(order, ["TODO", "CURRENT", "HISTORY"])
        by = {r["session_id"]: r for r in index}
        self.assertEqual((by["b"]["section"], by["b"]["home"]), ("TODO", "CURRENT"))
        self.assertEqual((by["d"]["section"], by["d"]["home"]), ("TODO", "HISTORY"))
        self.assertEqual(by["a"]["section"], "CURRENT")
        self.assertEqual(sum(1 for r in index if r["session_id"] == "b"), 1)

    def test_no_todo_no_section(self):
        text, _ = sl.render_list([_row("a", kind="live")], [], [], set(), cols=100)
        self.assertNotIn("TODO", text)

    def test_a_chain_is_parked_by_any_of_its_ids(self):
        here = [_row("new", chain_ids=["old", "new"])]
        _t, index = sl.render_list([], here, [], set(), cols=100, todo={"old"})
        self.assertEqual(index[0]["section"], "TODO")


class TodoStoreTest(unittest.TestCase):
    def setUp(self):
        self.proj = tempfile.mkdtemp(prefix="submarine-todo-")

    def test_round_trip_and_snapshots_survive_a_star_change(self):
        records.save_todos({"x"}, self.proj, records={"x": {"name": "parked"}})
        self.assertEqual(records.load_todos(self.proj), {"x"})
        records.toggle_bookmark("y", self.proj, record={"name": "starred"})
        records.toggle_bookmark("y", self.proj)            # unstar
        self.assertEqual(records.load_bookmark_records(self.proj).get("x"),
                         {"name": "parked"}, "a star change dropped the TODO snapshot")
        records.save_todos(set(), self.proj)
        self.assertEqual(records.load_todos(self.proj), set())
        self.assertNotIn("x", records.load_bookmark_records(self.proj))

    def test_closing_a_parked_history_row_removes_it_like_history(self):
        calls = []
        orig = sl.remove_saved_session
        sl.remove_saved_session = lambda sid: calls.append(sid) or True
        try:
            sl.close_row(None, {"kind": "saved", "session_id": "h1",
                                "section": "TODO", "home": "HISTORY"})
        except Exception:
            pass
        finally:
            sl.remove_saved_session = orig
        self.assertIn("h1", calls)


if __name__ == "__main__":
    unittest.main()
