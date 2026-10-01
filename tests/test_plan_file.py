"""View Plan with an ExitPlanMode that names no file (Claude Code 2.1.284
may call it with empty input): the plan is found where the CLI wrote it."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rewind import plan_file_from_transcript  # noqa: E402
from tests.fakes import FakeClient, make_session  # noqa: E402


def _fixture():
    root = tempfile.mkdtemp(prefix="submarine-plan-")
    os.makedirs(os.path.join(root, "plans"))
    for slug in ("old-slug", "live-slug"):
        with open(os.path.join(root, "plans", slug + ".md"), "w") as f:
            f.write("# plan %s\n" % slug)
    jsonl = os.path.join(root, "t.jsonl")
    with open(jsonl, "w") as f:
        for slug in ("old-slug", "live-slug"):
            f.write(json.dumps({"type": "user", "slug": slug}) + "\n")
    return root, jsonl


class TranscriptSlugTest(unittest.TestCase):
    def test_the_last_slug_names_the_plan(self):
        root, jsonl = _fixture()
        self.assertEqual(plan_file_from_transcript(jsonl, config_dir=root),
                         os.path.join(root, "plans", "live-slug.md"))

    def test_nothing_to_find(self):
        root, _jsonl = _fixture()
        self.assertEqual(plan_file_from_transcript(None, config_dir=root), "")
        empty = os.path.join(root, "e.jsonl")
        open(empty, "w").close()
        self.assertEqual(plan_file_from_transcript(empty, config_dir=root), "")


class EmptyExitPlanModeTest(unittest.TestCase):
    def test_the_request_gets_the_resolved_file_and_answers_with_it(self):
        root, _jsonl = _fixture()
        plan = os.path.join(root, "plans", "live-slug.md")
        client = FakeClient()
        s = make_session(initialized=True, client=client, backend="claude")
        s._resolve_plan_file = lambda: plan
        s.events.resolve_plan_file = s._resolve_plan_file
        s.query("plan it")
        s.events.plan_mode_exit({"id": "p1", "tool_input": {}})
        (_pid, plan_file, _allowed, cb), = s.output.plans
        self.assertEqual(plan_file, plan)
        cb("approve")
        sent = [p for m, p, _cb in client.sent if m == "plan_response"][-1]
        self.assertEqual(sent["planFilePath"], plan)
        self.assertEqual(sent["plan"], "# plan live-slug\n")

    def test_a_named_file_wins(self):
        client = FakeClient()
        s = make_session(initialized=True, client=client, backend="claude")
        s.events.resolve_plan_file = lambda: "/should/not/be/used.md"
        s.query("plan it")
        s.events.plan_mode_exit({"id": "p1", "tool_input": {
            "plan": "x", "planFilePath": "/named/plan.md"}})
        self.assertEqual(s.output.plans[0][1], "/named/plan.md")


if __name__ == "__main__":
    unittest.main()
