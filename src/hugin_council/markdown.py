"""Just enough markdown colouring for reading a synthesis in a terminal.

Deliberately small and dependency-free. The synthesis is prose with headings,
numbered options, emphasis and the occasional code span; anything more elaborate
than that is not what this tool produces, and a full renderer would be a
liability the first time a model emits something odd.

Everything degrades to plain text when colour is off, so piping stays useful.
"""

from __future__ import annotations

import re
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


def render(text: str, colour: bool = True, theme: Theme = THEME) -> str:
    if not colour:
        return text
    heads = (theme.h1, theme.h2, theme.h3)
    out: list[str] = []
    in_fence = False

    for line in text.splitlines():
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
