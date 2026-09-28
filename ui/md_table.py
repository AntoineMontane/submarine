"""Markdown tables in the sheet: the raw text stays, a popup lays them out.

A complete table gets a `⊞ table R×C …` hint above it. Hovering the table,
or clicking the hint, opens a popup with the table drawn as cells.

Widths are pixels. A CJK glyph from a fallback font is not two columns of the
editor font (15px against an 8px em, measured), so padding with spaces can't
line anything up. Every character the popup shows is already in the buffer,
in the raw table, so its advance is read from the view with text_to_layout.
Cells are inline blocks of a fixed pixel width, with CSS borders.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

_SEP_CELL = re.compile(r"^\s*:?-{1,}:?\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__)")
MIN_COL = 6         # columns (in ems) before the table goes stacked
WORD_CAP = 18       # a word longer than this many ems may break in its cell


# ── Parsing ────────────────────────────────────────────────────────────────

def split_row(line: str) -> List[str]:
    """Cells of a `| a | b |` row. `\\|` and pipes inside `code` stay."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, buf, in_code, i = [], [], False, 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _is_sep(line: str) -> bool:
    if "-" not in line or "|" not in line:
        return False
    cells = split_row(line)
    return bool(cells) and all(_SEP_CELL.match(c) for c in cells)


def _align(cell: str) -> str:
    c = cell.strip()
    if c.startswith(":") and c.endswith(":"):
        return "c"
    if c.endswith(":"):
        return "r"
    return "l"


class Table:
    """One table found in a text block. Lines are block-relative."""

    __slots__ = ("first", "last", "header", "aligns", "rows")

    def __init__(self, first, last, header, aligns, rows):
        self.first = first
        self.last = last
        self.header = header
        self.aligns = aligns
        self.rows = rows

    @property
    def label(self) -> str:
        return "⊞ table %d×%d …" % (len(self.rows), len(self.header))


def find_tables(lines: List[str], final: bool = False) -> List[Table]:
    """Complete tables in `lines`: header, `|---|` separator, body rows.

    A table is complete when a non-row line follows it, or when `final`
    (the text will not grow). Fenced code is skipped.
    """
    out, i, n, fence = [], 0, len(lines), None
    while i < n:
        line = lines[i]
        m = _FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            i += 1
            continue
        if fence or "|" not in line or i + 1 >= n or not _is_sep(lines[i + 1]):
            i += 1
            continue
        header = split_row(line)
        aligns = [_align(c) for c in split_row(lines[i + 1])]
        if len(aligns) != len(header):
            i += 1
            continue
        j = i + 2
        rows = []
        while j < n and "|" in lines[j] and lines[j].strip():
            rows.append(split_row(lines[j]))
            j += 1
        if j < n or final:
            out.append(Table(i, j - 1, header, aligns, rows))
        i = j
    return out


# ── Widths ─────────────────────────────────────────────────────────────────

class Metrics:
    """Character advances in px. Unmeasured: em, or two for wide glyphs."""

    def __init__(self, em: float = 8.0, px: Optional[Dict[str, float]] = None):
        self.em = float(em or 8.0)
        self.px = dict(px or {})

    def char(self, ch: str) -> float:
        w = self.px.get(ch)
        if w is not None:
            return w
        if unicodedata.combining(ch) or ch in "​‍️︎":
            return 0.0
        wide = unicodedata.east_asian_width(ch) in ("W", "F")
        return self.em * (2 if wide else 1)

    def text(self, s: str) -> float:
        return sum(self.char(c) for c in s)


def measure_view(view, a: int, b: int) -> Metrics:
    """Advances of the characters in [a, b), read from the view's layout."""
    m = Metrics(view.em_width())
    try:
        text = view.substr(_region(a, b))
    except Exception:
        return m
    for k, ch in enumerate(text):
        if ch in m.px or ch == "\n":
            continue
        try:
            x0, y0 = view.text_to_layout(a + k)
            x1, y1 = view.text_to_layout(a + k + 1)
        except Exception:
            continue
        if y0 == y1 and x1 > x0:     # same visual line: a real advance
            m.px[ch] = x1 - x0
    return m


def _region(a, b):
    import sublime
    return sublime.Region(a, b)


# ── Inline markup ──────────────────────────────────────────────────────────

Run = Tuple[str, str]    # (text, style) — style '' | 'code' | 'b'


def runs(cell: str) -> List[Run]:
    out = []
    for part in _INLINE.split(cell):
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append((part[1:-1], "code"))
        elif part[:2] in ("**", "__") and len(part) > 4:
            out.append((part[2:-2], "b"))
        else:
            out.append((part, ""))
    return out


def plain(cell: str) -> str:
    return "".join(t for t, _ in runs(cell))


# ── Layout ─────────────────────────────────────────────────────────────────

def wrap_runs(rs: List[Run], width: float, m: Metrics) -> List[List[Run]]:
    """Wrap styled runs to `width` px → lines of runs."""
    lines, cur, w = [], [], 0.0
    space = m.char(" ")
    tokens = [(tok, style) for text, style in rs
              for tok in re.findall(r"\S+|\s+", text)]
    for tok, style in tokens:
        tw = m.text(tok)
        if tok.isspace():
            if w and w + space <= width:
                cur.append((" ", style))
                w += space
            continue
        if w + tw > width and w:
            lines.append(cur)
            cur, w = [], 0.0
        while tw > width:              # a word wider than the column
            piece, pw = "", 0.0
            for ch in tok:
                if piece and pw + m.char(ch) > width:
                    break
                piece += ch
                pw += m.char(ch)
            cur.append((piece, style))
            lines.append(cur)
            cur, w = [], 0.0
            tok = tok[len(piece):]
            tw = m.text(tok)
        if tok:
            cur.append((tok, style))
            w += tw
    if cur or not lines:
        lines.append(cur)
    for ln in lines:
        while ln and ln[-1][0] == " ":
            ln.pop()
    return lines


def fit_widths(natural: List[float], floors: List[float],
               target: float) -> Optional[List[float]]:
    """Column widths within `target` px, or None (go stacked).

    Water level: each column gets min(natural, level), never below its floor
    (its longest word, capped), with the level as high as fits.
    """
    if sum(natural) <= target:
        return list(natural)
    if sum(floors) > target:
        return None
    lo, hi = 0, int(max(natural)) + 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if sum(max(f, min(n, mid)) for n, f in zip(natural, floors)) <= target:
            lo = mid
        else:
            hi = mid - 1
    widths = [max(f, min(n, lo)) for n, f in zip(natural, floors)]
    spare = target - sum(widths)
    for i in sorted(range(len(widths)), key=lambda i: widths[i] - natural[i]):
        if spare <= 0:
            break
        add = min(spare, natural[i] - widths[i])
        widths[i] += add
        spare -= add
    return widths


def pad_px(m: Metrics) -> int:
    return int(m.em * 0.8)


def layout(t: Table, budget: float, m: Metrics):
    """("grid", widths, [(cells, is_header)]) or ("stacked", keyw, valw, blocks).

    Cells are lists of wrapped lines. `budget` is the popup width in px.
    """
    ncol = len(t.header)
    rows = [(r + [""] * ncol)[:ncol] for r in t.rows]
    every = [t.header] + rows

    def longest_word(cell):
        return max([m.text(w) for w in plain(cell).split()] or [m.em])

    natural = [max(m.em, max(m.text(plain(r[c])) for r in every)) for c in range(ncol)]
    floors = [min(n, max(MIN_COL * m.em, min(WORD_CAP * m.em,
                                             max(longest_word(r[c]) for r in every))))
              for c, n in enumerate(natural)]
    target = budget - ncol * (2 * pad_px(m) + 1) - 1
    widths = fit_widths(natural, floors, target)
    if widths is None:
        keyw = min(max([m.text(plain(h)) for h in t.header[1:]] or [0.0]), budget / 3)
        valw = max(MIN_COL * m.em, budget - keyw - 3 * pad_px(m))
        blocks = []
        for r in rows:
            blocks.append((wrap_runs(runs(r[0]), budget - pad_px(m), m),
                           [(wrap_runs(runs(h), keyw, m), wrap_runs(runs(v), valw, m))
                            for h, v in zip(t.header[1:], r[1:])]))
        return ("stacked", keyw, valw, blocks)
    body = [([wrap_runs(runs(c), widths[i], m) for i, c in enumerate(r)], k == 0)
            for k, r in enumerate(every)]
    return ("grid", widths, body)


# ── HTML ───────────────────────────────────────────────────────────────────

_CSS = """
  body { margin: 0; padding: 0.2rem 0 0.3rem 0; }
  .dim { color: color(var(--foreground) alpha(0.4)); }
  .code { color: var(--bluish); }
  .hd { color: var(--foreground); }
  a.hint { text-decoration: none; color: color(var(--foreground) alpha(0.45)); }
  .tbl { border: 1px solid color(var(--foreground) alpha(0.25)); }
  .row { border-top: 1px solid color(var(--foreground) alpha(0.12)); }
  .row.first { border-top: none; border-bottom: 1px solid color(var(--foreground) alpha(0.35)); }
  .c { display: inline-block; border-left: 1px solid color(var(--foreground) alpha(0.25)); }
  .c.first { border-left: none; }
"""


def _line_html(seg: List[Run], cls: str = "") -> str:
    parts = []
    for text, s in seg:
        # Bold glyphs may be wider than the measured regular ones: no bold.
        style = "code" if s == "code" else ""
        c = " ".join(x for x in (style, cls) if x)
        t = html.escape(text).replace(" ", "&nbsp;")
        parts.append('<span class="%s">%s</span>' % (c, t) if c else t)
    return "".join(parts) or "&nbsp;"


def _padded(lines: List[str], height: int) -> str:
    # minihtml ignores `height` on inline blocks: pad with blank lines, or a
    # short cell bottom-aligns and its border stops short.
    return "<br>".join(lines + ["&nbsp;"] * (height - len(lines)))


def hint_html(t: Table, href: str) -> str:
    return ('<body id="submarine-table-hint"><style>%s</style>'
            '<a class="hint" href="%s">%s</a></body>'
            % (_CSS, html.escape(href), html.escape(t.label)))


def table_html(t: Table, budget: float, m: Metrics) -> str:
    shape = layout(t, budget, m)
    pad = pad_px(m)
    out = []
    if shape[0] == "grid":
        _, widths, body = shape
        out.append('<div class="tbl">')
        for cells, is_head in body:
            height = max(len(c) for c in cells)
            out.append('<div class="row%s">' % (" first" if is_head else ""))
            for i, lines in enumerate(cells):
                inner = []
                for seg in lines:
                    free = max(0.0, widths[i] - sum(m.text(x) for x, _ in seg))
                    a = t.aligns[i] if i < len(t.aligns) else "l"
                    lead = free / 2 if a == "c" else (free if a == "r" else 0)
                    inner.append('<span style="padding-left: %dpx">%s</span>'
                                 % (int(lead), _line_html(seg, "hd" if is_head else "")))
                out.append('<span class="c%s" style="width: %dpx; padding: 0 %dpx">%s</span>'
                           % (" first" if i == 0 else "", int(widths[i] + 1), pad,
                              _padded(inner, height)))
            out.append("</div>")
        out.append("</div>")
    else:
        _, keyw, valw, blocks = shape
        for title, pairs in blocks:
            out.append('<div class="tbl" style="padding: 0.2rem %dpx; margin-bottom: 0.3rem">'
                       % pad)
            out.append("<br>".join(_line_html(seg, "hd") for seg in title))
            for key, val in pairs:
                h = max(len(key), len(val))
                out.append('<div><span class="c first dim" style="width: %dpx">%s</span>'
                           '<span class="c first" style="width: %dpx; padding-left: %dpx">%s</span></div>'
                           % (int(keyw + 1), _padded([_line_html(s) for s in key], h),
                              int(valw + 1), pad, _padded([_line_html(s) for s in val], h)))
            out.append("</div>")
    return ('<body id="submarine-table"><style>%s</style>%s</body>'
            % (_CSS, "".join(out)))


# ── Locating tables in the sheet ───────────────────────────────────────────

class Placed:
    """A table and where its raw text sits in the buffer."""

    __slots__ = ("table", "start", "end")

    def __init__(self, table: Table, start: int, end: int):
        self.table = table
        self.start = start
        self.end = end


def place_tables(content: str, blocks: List[Tuple[str, bool, int]]) -> List[Placed]:
    """Find each block's tables in `content` (the buffer text).

    `blocks` are (text, final, search_from) in buffer order; the sheet writes
    a text block verbatim, so a table's raw lines are found as written.
    """
    out = []
    pos = 0
    for text, final, lower in blocks:
        if "|" not in text or "-" not in text:
            continue
        lines = text.split("\n")
        for t in find_tables(lines, final=final):
            raw = "\n".join(lines[t.first:t.last + 1])
            at = content.find(raw, max(pos, lower or 0))
            if at < 0:
                continue
            out.append(Placed(t, at, at + len(raw)))
            pos = at + len(raw)
    return out
