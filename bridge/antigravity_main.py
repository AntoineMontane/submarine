"""Google Antigravity ACP bridge — thin adapter over AcpBridge.

Spawns Google's official `agy_acp_server.par` (ACP Registry id
`antigravity-acp`) over stdio, installing it from Google's CDN on first use.
Sign-in is the user's Google account (`oauth-personal`): the first start
opens a browser once; later starts reuse ~/.gemini/antigravity-acp/.
MCP goes over HTTP (the server takes no stdio MCP).
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

_BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_DIR = os.path.dirname(_BRIDGE_DIR)
sys.path.insert(0, _BRIDGE_DIR)
sys.path.insert(0, _PLUGIN_DIR)

from acp_base import AcpBridge, run_bridge  # noqa: E402
from acp.http_mcp import HttpMcpMixin  # noqa: E402
from backend import antigravity as ag  # noqa: E402
from rpc_helpers import send_notification  # noqa: E402

# Sign-in methods the server advertises, in the order we try them: the
# Google account first (the user's plan), then what settings/env provide.
_RECOMMENDED = "(Recommended)"
_AUTH_ORDER = ("oauth-personal", "oauth-business", "gemini-api-key", "agent-platform")


class AntigravityBridge(HttpMcpMixin, AcpBridge):
    BACKEND_NAME = "antigravity"
    DEFAULT_MODEL = "gemini-3.8-flash-high"   # the server's own default
    # The server's modes: default (asks), auto_edit, yolo.
    PERM_TO_MODE = {
        "default": "default",
        "acceptEdits": "auto_edit",
        "auto": "yolo",
        "bypassPermissions": "yolo",
        "dontAsk": "yolo",
        "plan": "default",
    }
    MODE_TO_PERM = {
        "default": "default",
        "auto_edit": "acceptEdits",
        "yolo": "bypassPermissions",
    }
    LOG_PATH = os.path.join(
        os.environ.get("TMPDIR")
        or os.environ.get("TEMP")
        or os.environ.get("TMP")
        or "/tmp",
        "submarine_acp_bridge.log",
    )

    # Antigravity's tool ids → our formatters (unmapped ids show as-is).
    TOOL_TO_CANONICAL = {
        "view_file": "Read",
        "client_view_file": "Read",
        "write_to_file": "Write",
        "replace_file_content": "Edit",
        "multi_replace_file_content": "Edit",
        "sed_file": "Edit",
        "run_command": "Bash",
        "grep_search": "Grep",
        "find_by_name": "Glob",
        "find_file": "Glob",
        "list_dir": "Glob",
        "search_web": "WebSearch",
        "read_url_content": "WebFetch",
        "command_status": "TaskGet",
        "invoke_subagent": "Subagent",
        "browser_subagent": "Subagent",
        "ask_question": "AskUserQuestion",
        "notebook_edit": "NotebookEdit",
    }

    # Offered client fs, antigravity-acp 1.2.1 announces "client_view_file"
    # and never sends fs/read_text_file: the turn hangs. It reads files
    # itself when we don't offer it. (Terminal is fine: it runs commands
    # itself either way.)
    CLIENT_FS = False

    def __init__(self) -> None:
        super().__init__()
        self._server = ""

    def _ensure_server(self) -> str:
        if self._server:
            return self._server
        server = ag.resolve_server()
        if not server:
            self._notify("installing Google Antigravity's ACP server (one time, ~110 MB)…")
            server = ag.install(log=self.file_log)
            self._notify("Antigravity ACP server installed")
        self._server = server
        return server

    def _notify(self, text: str) -> None:
        self.file_log(text)
        send_notification("message", {"type": "system", "subtype": "init",
                                       "data": {"message": text}})

    def agent_argv(self) -> List[str]:
        return ag.agent_argv(self._ensure_server())

    def spawn_env(self) -> Optional[Dict[str, str]]:
        env = dict(os.environ)
        harness = ag.harness_path(self._ensure_server())
        if harness:
            env.setdefault("ANTIGRAVITY_HARNESS_PATH", harness)
        return env

    def _normalize_tool_name(self, upd: dict) -> str:
        """Titles are "Running <tool_id>" (find_file, view_file, …) or, for
        a shell command, the command line itself. The shared rules read the
        first as Bash and the second as a tool named after the command."""
        title = str(upd.get("title") or "").strip()
        if str(upd.get("toolCallId") or "").startswith("interaction_"):
            return "AskUserQuestion"            # the ask tool; title = question
        if title.startswith("Running "):
            tool_id = title[len("Running "):].split()[0] if title[8:].strip() else ""
            if tool_id:
                return self.TOOL_TO_CANONICAL.get(tool_id, tool_id)
        if (upd.get("kind") or "").lower() == "execute":
            return "Bash"
        return super()._normalize_tool_name(upd)

    def _tool_input_from_update(self, upd: dict, tool_name: str) -> dict:
        out = super()._tool_input_from_update(upd, tool_name)
        if tool_name == "AskUserQuestion" and not out.get("question"):
            q = str(upd.get("title") or "").strip().rstrip(":")
            if q:
                out["question"] = q
        return out

    # ── Questions ────────────────────────────────────────────────────
    # Antigravity's ask tool is a session/request_permission whose options
    # are the answers: question in the title, toolCallId "interaction_…",
    # ids "1", "2"…, every kind allow_once, no reject. The shared handler
    # cancelled it on sight ("missing options") or read only Kimi's ids.

    def _is_ask_user_permission(self, tool_name, options, tool_call=None) -> bool:
        tid = str((tool_call or {}).get("toolCallId") or "")
        if tid.startswith("interaction_"):
            return True
        return super()._is_ask_user_permission(tool_name, options, tool_call)

    async def _handle_acp_ask_user_permission(self, tool_call, options, tool_input):
        choices = [o for o in (options or []) if isinstance(o, dict)]
        opts = []
        for o in choices:
            name = str(o.get("name") or o.get("optionId") or "?")
            rec = name.startswith(_RECOMMENDED)
            opts.append({"label": name[len(_RECOMMENDED):].strip() if rec else name,
                         "description": "Recommended" if rec else ""})
        title = str(tool_call.get("title") or "").strip().rstrip(":")
        questions = [{"question": title or "Choose an option", "header": "",
                      "options": opts, "multiSelect": False}]
        answers = await self._ask_question_ui(questions)
        if answers is None:
            return {"outcome": {"outcome": "cancelled"}}
        label = self._first_answer_label(answers, questions)
        for i, opt in enumerate(opts):
            if self._labels_match(label, opt["label"]):
                self.file_log(f"ask_user selected {label!r} → {choices[i].get('optionId')!r}")
                return {"outcome": {"outcome": "selected",
                                    "optionId": choices[i].get("optionId")}}
        # A typed answer has no option to carry it: cancel the interaction,
        # and the shared follow-up sends the text as the next prompt.
        other = self._kimi_other_followup(questions, answers, label)
        if other:
            self._pending_ask_followup = other
        self.file_log(f"ask_user free text {label!r} → follow-up prompt")
        return {"outcome": {"outcome": "cancelled"}}

    def normalize_model(self, model: Optional[str]) -> str:
        return ag.normalize_model(model, default=self.DEFAULT_MODEL)

    async def after_agent_initialize(self, init_result: dict) -> None:
        """Select a sign-in method. With stored credentials this returns at
        once; without, `oauth-personal` opens the browser and waits for the
        user — no timeout, the host shows the session as starting."""
        methods = [m.get("id") for m in (init_result.get("authMethods")
                                         or self._auth_methods or [])
                   if isinstance(m, dict)]
        preferred = (os.environ.get("ANTIGRAVITY_AUTH_METHOD") or "").strip()
        if preferred not in methods:
            preferred = next((m for m in _AUTH_ORDER if m in methods), "")
        if not preferred:
            self.log("no auth methods advertised; relying on the server's settings")
            return
        if preferred == "oauth-personal" and not _has_token():
            self._notify("sign in to Google in your browser to start Antigravity…")
        try:
            await self._send_acp("authenticate", {"methodId": preferred})
            self.log(f"authenticated via {preferred}")
        except Exception as e:
            self.log(f"authenticate({preferred}) failed: {e}")


def _has_token() -> bool:
    home = os.environ.get("GEMINI_HOME") or os.path.join(os.path.expanduser("~"), ".gemini")
    return os.path.isfile(os.path.join(home, "antigravity-acp", "acp_token.json"))


def main() -> None:
    run_bridge(AntigravityBridge())


if __name__ == "__main__":
    main()
