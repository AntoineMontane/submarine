"""spawn_session refuses to fork a pi session: pi runs --no-session, so there
is nothing to copy, and the child came up empty under a placeholder id."""
import os
import sys
import types
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT,):
    if p not in sys.path:
        sys.path.insert(0, p)


class ForkPiTest(unittest.TestCase):
    def test_a_pi_source_is_refused_before_anything_is_created(self):
        from tests.stubs import install_sublime
        install_sublime()
        import mcp.socket_server as ss
        created = []
        src = types.SimpleNamespace(session_id="pi-session", backend="pi", model="m")
        saved = (ss._try_import, ss._get_session_by_agent_id)
        ss._try_import = lambda name: (lambda *a, **k: created.append(1))
        ss._get_session_by_agent_id = lambda aid: src
        try:
            srv = ss.MCPSocketServer.__new__(ss.MCPSocketServer)
            srv._get_window = lambda: object()
            srv._caller_agent_id = None
            out = srv._spawn_session("do it", fork_from_agent_id="submarine::piparent00001")
        finally:
            ss._try_import, ss._get_session_by_agent_id = saved
        self.assertIn("Cannot fork a pi session", out.get("error", ""))
        self.assertEqual(created, [])


if __name__ == "__main__":
    unittest.main()
