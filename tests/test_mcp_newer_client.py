"""A newer MCP client (Antigravity's harness, MCP 2026-07-28) connects.

It opens with `server/discover`, falls back to `initialize` on "method not
found", and GETs for an SSE stream. Our server answered nothing to the first
and the HTTP relay a bare 200 to the second: "still connecting" forever.
"""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(_ROOT, "mcp"), os.path.join(_ROOT, "bridge"), _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


class UnknownMethodTest(unittest.TestCase):
    def test_a_request_gets_method_not_found(self):
        import server
        r = server.handle_request({"jsonrpc": "2.0", "id": 7, "method": "server/discover"})
        self.assertEqual(r["id"], 7)
        self.assertEqual(r["error"]["code"], -32601)

    def test_a_notification_gets_nothing(self):
        import server
        self.assertIsNone(server.handle_request(
            {"jsonrpc": "2.0", "method": "notifications/something"}))


class RelayTest(unittest.TestCase):
    def test_get_is_405_and_post_round_trips(self):
        from stdio_http_mcp import start_stdio_http_mcp
        echo = ("import sys, json\n"
                "for l in sys.stdin:\n"
                "    m = json.loads(l)\n"
                "    if 'id' in m: print(json.dumps({'jsonrpc': '2.0', 'id': m['id'], 'result': {}}), flush=True)\n")
        url, httpd = start_stdio_http_mcp(sys.executable, ["-c", echo], {})
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(urllib.request.Request(
                    url, headers={"Accept": "text/event-stream"}), timeout=5)
            self.assertEqual(ctx.exception.code, 405)
            req = urllib.request.Request(
                url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["id"], 1)
        finally:
            httpd.shutdown()
            httpd.child.close()


if __name__ == "__main__":
    unittest.main()
