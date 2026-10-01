#!/usr/bin/env python3
"""Live Antigravity: drive the real `bridge/antigravity_main.py` through one turn.

Needs the server installed (or the network, to install it) and a Google
sign-in under ~/.gemini/antigravity-acp/ (the first run opens a browser).
Throwaway workspace; asks the agent to read a file and say what is in it.
Reuses the claude_bg sandbox's NDJSON bridge client.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_BRIDGE = os.path.join(_ROOT, "bridge")
sys.path.insert(0, _ROOT)

from sandbox.claude_bg.check_e2e import Bridge  # noqa: E402


def main() -> int:
    work = tempfile.mkdtemp(prefix="agy-e2e-")
    with open(os.path.join(work, "note.txt"), "w") as f:
        f.write("the secret word is walrus\n")
    env = dict(os.environ, SUBMARINE_SANDBOX="antigravity")
    bridge = Bridge([sys.executable, os.path.join(_BRIDGE, "antigravity_main.py")],
                    cwd=work, env=env)
    try:
        init = bridge.request("initialize", {
            "cwd": work, "model": "gemini-3.8-flash-low",
            "permission_mode": "bypassPermissions", "allowed_tools": [],
            "agent_id": "submarine::agye2e000001",
        }, timeout=600)
        print("initialize:", json.dumps(init.get("result") or init.get("error"))[:500])
        if init.get("error"):
            return 2
        res = bridge.request("query", {
            "prompt": "Run `echo agy-shell-ok` in the shell, then read note.txt. Reply with the shell output and the secret word, nothing else."},
            timeout=240)
        print("query:", json.dumps(res.get("result") or res.get("error"))[:300])
        text, tools = "", []
        for _t, kind, p in bridge.events:
            if kind != "notify":
                continue
            if p.get("type") == "text_delta":
                text += p.get("text") or ""
            elif p.get("type") == "tool_use":
                tools.append((p.get("name"), json.dumps(p.get("input"))[:120]))
            elif p.get("type") == "system":
                print("system:", p.get("subtype"), json.dumps(p.get("data"))[:160])
        for t in tools:
            print("tool:", *t)
        print("text:", repr(text[:200]))
        ok = "walrus" in text.lower()
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        bridge.close()
        if bridge.stderr:
            print("stderr tail:", *bridge.stderr[-5:], sep="\n  ")


if __name__ == "__main__":
    sys.exit(main())
