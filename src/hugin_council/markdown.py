"""Just enough markdown colouring for reading a synthesis in a terminal.

Deliberately small and dependency-free. The synthesis is prose with headings,
numbered options, emphasis and the occasional code span; anything more elaborate
than that is not what this tool produces, and a full renderer would be a
liability the first time a model emits something odd.

Everything degrades to plain text when colour is off, so piping stays useful.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass

RESET = "\x1b[0m"


@dataclass(frozen=True)
class Theme:
    h1: str = "\x1b[1;38;5;39m"
    h2: str = "\x1b[1;38;5;75m"
    h3: str = "\x1b[1;38;5;110m"
    bold: str = "\x1b[1m"
    italic: str = "\x1b[3m"
    code: str = "\x1b[38;5;180m"
    fence: str = "\x1b[38;5;108m"
    bullet: str = "\x1b[38;5;244m"
    quote: str = "\x1b[38;5;245m"
    rule: str = "\x1b[38;5;240m"
    link: str = "\x1b[4;38;5;81m"
    dim: str = "\x1b[2m"
    table: str = "\x1b[38;5;240m"
    header: str = "\x1b[1;38;5;252m"


THEME = Theme()

_FENCE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_ORDERED = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_QUOTE = re.compile(r"^(\s*>+)\s?(.*)$")

# Inline: code spans first, so emphasis inside them is left alone.
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)|(?<![_\w])_([^_\n]+)_(?!\w)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

_PLACEHOLDER = "\x00{}\x00"

_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _visible(text: str) -> int:
    return len(_ANSI.sub("", text))


def _cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    # A pipe inside a code span is not a column boundary.
    parts, buf, in_code = [], "", False
    for ch in body:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    parts.append(buf.strip())
    return parts


def _alignments(sep: str, count: int) -> list[str]:
    out = []
    for cell in _cells(sep):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("centre" if left and right else "right" if right else "left")
    return (out + ["left"] * count)[:count]


def _pad(text: str, width: int, align: str) -> str:
    gap = width - _visible(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "centre":
        return " " * (gap // 2) + text + " " * (gap - gap // 2)
    return text + " " * gap


def _table(lines: list[str], theme: Theme, width: int) -> list[str]:
    """Align a pipe table into columns, header bold, rules dim.

    Synthesis tables are trade-off grids: a few columns, short cells. When the
    aligned form would not fit the terminal the rows are left as written, with
    inline spans coloured, since a wrapped grid is worse than a raw one.
    """
    rows = [_cells(line) for i, line in enumerate(lines) if i != 1]
    count = max(len(r) for r in rows)
    rows = [r + [""] * (count - len(r)) for r in rows]
    aligns = _alignments(lines[1], count)
    rendered = [[_inline(cell, theme) for cell in row] for row in rows]
    widths = [max(_visible(row[c]) for row in rendered) for c in range(count)]
    if sum(widths) + 3 * count + 1 > width:
        return [_inline(line, theme) for line in lines]
    bar = f"{theme.table}│{RESET}"
    out = []
    for index, row in enumerate(rendered):
        cells = [_pad(cell, widths[c], aligns[c]) for c, cell in enumerate(row)]
        if index == 0:
            cells = [f"{theme.header}{cell}{RESET}" for cell in cells]
        out.append(f"{bar} " + f" {bar} ".join(cells) + f" {bar}")
        if index == 0:
            rule = f"{theme.table}┼{RESET}".join(
                f"{theme.table}{'─' * (w + 2)}{RESET}" for w in widths
            )
            out.append(f"{theme.table}├{RESET}{rule}{theme.table}┤{RESET}")
    return out


def _inline(text: str, theme: Theme) -> str:
    """Emphasis, code spans and links.

    Code spans are lifted out first and put back last so that a `*` inside
    backticks is not read as emphasis.
    """
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(f"{theme.code}{match.group(1)}{RESET}")
        return _PLACEHOLDER.format(len(spans) - 1)

    text = _CODE.sub(stash, text)
    text = _LINK.sub(lambda m: f"{theme.link}{m.group(1)}{RESET}{theme.dim} ({m.group(2)}){RESET}", text)
    text = _BOLD.sub(lambda m: f"{theme.bold}{m.group(1) or m.group(2)}{RESET}", text)
    text = _ITALIC.sub(lambda m: f"{theme.italic}{m.group(1) or m.group(2)}{RESET}", text)
    for index, span in enumerate(spans):
        text = text.replace(_PLACEHOLDER.format(index), span)
    return text


def render(text: str, colour: bool = True, theme: Theme = THEME, width: int | None = None) -> str:
    if not colour:
        return text
    if width is None:
        width = shutil.get_terminal_size((100, 24)).columns
    heads = (theme.h1, theme.h2, theme.h3)
    out: list[str] = []
    in_fence = False
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        index += 1
        if (
            not in_fence
            and _TABLE_ROW.match(line)
            and index < len(lines)
            and _TABLE_SEP.match(lines[index])
        ):
            block = [line, lines[index]]
            index += 1
            while index < len(lines) and _TABLE_ROW.match(lines[index]):
                block.append(lines[index])
                index += 1
            out.extend(_table(block, theme, width))
            continue
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append(f"{theme.rule}{line}{RESET}")
            continue
        if in_fence:
            out.append(f"{theme.fence}{line}{RESET}")
            continue

        heading = _HEADING.match(line)
        if heading:
            level = min(len(heading.group(1)), 3) - 1
            colour = heads[level]
            # Inline spans inside a heading each end with a RESET, which would
            # drop the heading colour for the rest of the line, so re-arm it.
            body = _inline(heading.group(2), theme).replace(RESET, RESET + colour)
            out.append(f"{colour}{body}{RESET}")
            continue

        if _RULE.match(line):
            out.append(f"{theme.rule}{'─' * 60}{RESET}")
            continue

        quote = _QUOTE.match(line)
        if quote:
            body = _inline(quote.group(2), theme)
            out.append(f"{theme.quote}{quote.group(1)} {RESET}{theme.italic}{body}{RESET}")
            continue

        bullet = _BULLET.match(line)
        if bullet:
            indent, _, body = bullet.groups()
            out.append(f"{indent}{theme.bullet}•{RESET} {_inline(body, theme)}")
            continue

        ordered = _ORDERED.match(line)
        if ordered:
            indent, marker, body = ordered.groups()
            out.append(f"{indent}{theme.bullet}{marker}{RESET} {_inline(body, theme)}")
            continue

        out.append(_inline(line, theme))
    return "\n".join(out)
