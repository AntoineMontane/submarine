"""Our stdio MCP servers offered to an ACP agent as localhost HTTP.

For agents that take MCP over HTTP but not stdio: Kimi 0.37.2 throws on a
stdio relay at session/new, and Antigravity's ACP server advertises
`mcpCapabilities: {http, sse}` only. Each stdio server runs behind a small
HTTP front (`stdio_http_mcp`); identity is --agent-id= (never --view-id=).
"""
from __future__ import annotations


class HttpMcpMixin:
    """Overrides `_collect_mcp_servers`; place before AcpBridge in the bases."""

    def _collect_mcp_servers(self) -> list:
        cached = getattr(self, "_http_mcp_servers", None)
        if cached is not None:
            return cached
        stdio = super()._collect_mcp_servers()
        try:
            from stdio_http_mcp import start_stdio_http_mcp, acp_stdio_env
        except ImportError:
            from ..stdio_http_mcp import start_stdio_http_mcp, acp_stdio_env
        out = []
        held = []
        for s in stdio:
            if not isinstance(s, dict) or not s.get("command"):
                continue
            name = s.get("name") or "mcp"
            try:
                env = acp_stdio_env(s)
                if getattr(self, "_agent_id", None):
                    env.setdefault("SUBMARINE_AGENT_ID", str(self._agent_id))
                url, httpd = start_stdio_http_mcp(
                    s["command"], list(s.get("args") or []), env)
                held.append(httpd)
                out.append({"name": name, "type": "http", "url": url, "headers": []})
                self.file_log(f"MCP http wrap {name} → {url}")
            except Exception as e:
                self.file_log(f"MCP http wrap {name}: {e}")
        # session.py stops these on shutdown.
        self._http_mcp_httpd = held
        self._http_mcp_servers = out
        return out
