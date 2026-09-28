"""Small helpers with callers in plat/ (and later core/). Sublime-free."""
from __future__ import annotations

import os
import re
import tempfile
from typing import Any, Dict


def temp_dir() -> str:
    """Process temp directory (TMPDIR / TEMP / TMP, else the system default)."""
    return (
        os.environ.get("TMPDIR")
        or os.environ.get("TEMP")
        or os.environ.get("TMP")
        or tempfile.gettempdir()
    )


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-copy `base`, then overlay `override`. Nested dicts merge one level.

    Used by the Claude CLI settings cascade. List / scalar values are replaced,
    not concatenated.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


_SURROGATE = re.compile("[\ud800-\udfff]")


def buffer_safe(text: str) -> str:
    """Text Sublime can hold: each lone surrogate becomes one U+FFFD.

    A stray byte decoded with `surrogateescape` (0xb3 → U+DCB3), or an emoji
    cut in half by a UTF-16 truncation, reaches the buffer as invalid UTF-8.
    From then on every read that spans it (`view.substr`) raises
    UnicodeDecodeError: a clear, a repaint, the next streamed delta. One
    character for one keeps the length, so offsets taken from the model
    still match the buffer.
    """
    if not isinstance(text, str):
        return text
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return _SURROGATE.sub("\ufffd", text)
