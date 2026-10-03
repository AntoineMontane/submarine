"""Google Antigravity via its official ACP server — pure Python (no Sublime).

Google publishes `antigravity-acp` in the ACP Registry: a self-contained
`agy_acp_server.par` (with `localharness_external` beside it) on its CDN. It
speaks ACP over stdio and signs in with a Google account (`oauth-personal`),
so sessions run on the user's Antigravity plan, not a Gemini API key.

Install location: ~/.submarine/agents/antigravity-acp/<version>/.
`$ANTIGRAVITY_ACP_BIN` points at a server elsewhere.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import zipfile
from typing import List, Optional, Tuple

VERSION = "1.2.1"
REGISTRY_ID = "antigravity-acp"
_CDN = "https://dl.google.com/agy-extensions/releases"
_ARCHIVES = {
    ("darwin", "arm64"): "macos/agy-acp-server-%s-darwin-arm64.zip",
    ("darwin", "x86_64"): "macos/agy-acp-server-%s-darwin-x86_64.zip",
    ("linux", "x86_64"): "linux/agy-acp-server-%s-linux-x86_64.zip",
    ("linux", "arm64"): "linux/agy-acp-server-%s-linux-arm64.zip",
    ("win32", "x86_64"): "windows/agy-acp-server-%s-windows-x86_64.zip",
    ("win32", "arm64"): "windows/agy-acp-server-%s-windows-arm64.zip",
}
_SERVER = "agy_acp_server.exe" if sys.platform == "win32" else "agy_acp_server.par"
_HARNESS = ("localharness_external.exe", "localharness.exe") if sys.platform == "win32" \
    else ("localharness_external", "localharness")

# What antigravity-acp 1.2.1 offers a personal Google account (session/new
# availableModels). The live list is merged in once a session runs.
ANTIGRAVITY_MODELS = [  # type: List[Tuple[str, str]]
    ("gemini-3.8-flash-high", "Gemini 3.8 Flash (High)"),
    ("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)"),
    ("gemini-3.8-flash-low", "Gemini 3.8 Flash (Low)"),
    ("gemini-pro-agent", "Gemini 3.1 Pro (High)"),
    ("gemini-3.1-pro-low", "Gemini 3.1 Pro (Low)"),
    ("gemini-3.7-flash-high", "Gemini 3.7 Flash (High)"),
    ("gemini-3.6-flash-high", "Gemini 3.6 Flash (High)"),
]


def install_root() -> str:
    return os.path.join(os.path.expanduser("~"), ".submarine", "agents", REGISTRY_ID)


def _platform_key() -> Tuple[str, str]:
    osname = "darwin" if sys.platform == "darwin" else (
        "win32" if sys.platform == "win32" else "linux")
    mach = platform.machine().lower()
    arch = "arm64" if mach in ("arm64", "aarch64") else "x86_64"
    return osname, arch


def archive_url(version: str = VERSION) -> Optional[str]:
    path = _ARCHIVES.get(_platform_key())
    return "%s/%s" % (_CDN, path % version) if path else None


def resolve_server() -> str:
    """The server executable, or "" when none is installed."""
    env = (os.environ.get("ANTIGRAVITY_ACP_BIN") or "").strip()
    if env and os.path.isfile(env):
        return env
    exe = os.path.join(install_root(), VERSION, _SERVER)
    return exe if os.path.isfile(exe) else ""


def harness_path(server: str) -> str:
    """`localharness_external` beside the server (it finds it the same way)."""
    base = os.path.dirname(server or "")
    for name in _HARNESS:
        cand = os.path.join(base, name)
        if os.path.isfile(cand):
            return cand
    return ""


def antigravity_available() -> bool:
    """Installed, or installable here (the bridge installs on first start)."""
    return bool(resolve_server() or archive_url())


def install(version: str = VERSION, log=None) -> str:
    """Download and unpack the server from Google's CDN. Returns its path."""
    url = archive_url(version)
    if not url:
        raise RuntimeError("Antigravity ACP has no build for %s/%s" % _platform_key())
    dest = os.path.join(install_root(), version)
    os.makedirs(install_root(), exist_ok=True)
    if log:
        log("downloading %s" % url)
    from urllib.request import urlopen
    tmp_dir = tempfile.mkdtemp(prefix="agy-acp-", dir=install_root())
    try:
        zpath = os.path.join(tmp_dir, "server.zip")
        with urlopen(url, timeout=60) as r, open(zpath, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        unpacked = os.path.join(tmp_dir, "unpacked")
        with zipfile.ZipFile(zpath) as z:
            z.extractall(unpacked)
        for name in os.listdir(unpacked):
            p = os.path.join(unpacked, name)
            if os.path.isfile(p):
                os.chmod(p, 0o755)
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        os.replace(unpacked, dest)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    exe = os.path.join(dest, _SERVER)
    if not os.path.isfile(exe):
        raise RuntimeError("%s missing from %s" % (_SERVER, url))
    return exe


def agent_argv(server: str) -> List[str]:
    """Absolute path: the server finds its harness beside argv[0]."""
    return [os.path.abspath(server)]


def normalize_model(model: Optional[str], default: str = "") -> str:
    key = (model or "").strip()
    if not key or key == "default":
        return default
    return key


def conversations_dir(gemini_home: Optional[str] = None) -> str:
    home = gemini_home or os.environ.get("GEMINI_HOME") or os.path.join(
        os.path.expanduser("~"), ".gemini")
    return os.path.join(home, "antigravity-acp", "conversations")


def fork_conversation(source_id: str, gemini_home: Optional[str] = None) -> str:
    """Copy a conversation to a new session id; returns the new id.

    antigravity-acp answers session/fork with an empty result, so a fork is
    made the way Grok's `_x.ai/session/fork` makes one: a copy on disk,
    then session/load. Each conversation is `<id>.db` (SQLite) + `<id>.meta`
    (its cwd); the id is also written inside, as a 36-char UUID string in
    trajectory_meta and in protobuf blobs. Swapping it for another UUID
    keeps every length, so the blobs stay valid. The backup API takes a
    consistent snapshot even while the source is in use.
    """
    import sqlite3
    import uuid
    base = conversations_dir(gemini_home)
    src_db = os.path.join(base, source_id + ".db")
    if not os.path.isfile(src_db):
        raise FileNotFoundError(src_db)
    new_id = str(uuid.uuid4())
    dst_db = os.path.join(base, new_id + ".db")
    src = sqlite3.connect("file:%s?mode=ro" % src_db, uri=True)
    dst = sqlite3.connect(dst_db)
    try:
        src.backup(dst)
        old_b, new_b = source_id.encode(), new_id.encode()
        tables = [r[0] for r in dst.execute(
            "select name from sqlite_master where type='table'")]
        for table in tables:
            cols = [r[1] for r in dst.execute("pragma table_info(`%s`)" % table)]
            for row in dst.execute("select rowid, * from `%s`" % table).fetchall():
                upd = {}
                for col, val in zip(cols, row[1:]):
                    if isinstance(val, bytes) and old_b in val:
                        upd[col] = val.replace(old_b, new_b)
                    elif isinstance(val, str) and source_id in val:
                        upd[col] = val.replace(source_id, new_id)
                if upd:
                    dst.execute(
                        "update `%s` set %s where rowid=?" % (
                            table, ", ".join("`%s`=?" % c for c in upd)),
                        (*upd.values(), row[0]))
        dst.commit()
    except Exception:
        dst.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(dst_db + suffix)
            except OSError:
                pass
        raise
    finally:
        src.close()
    dst.close()
    meta = os.path.join(base, source_id + ".meta")
    if os.path.isfile(meta):
        shutil.copyfile(meta, os.path.join(base, new_id + ".meta"))
    return new_id
