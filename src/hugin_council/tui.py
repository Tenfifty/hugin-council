"""The interactive shell: a prompt with a two-line ANSI status bar, and Tab.

Not a full-screen application on purpose. A synthesis is long prose you want to
scroll back through, and a full-screen frame throws the terminal's scrollback
away. So this is a normal scrolling terminal with a status bar pinned under the
prompt, which is what prompt_toolkit's bottom toolbar gives.

Falls back to plain ``input()`` when prompt_toolkit is missing or stdin is not a
terminal, in which case Tab is unavailable and the slash commands are the only
way to switch mode. The piped case matters: prompt_toolkit warns and misbehaves
on a non-tty, and driving the shell from a here-doc is how it gets tested.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

try:  # prompt_toolkit is a soft dependency
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings

    HAVE_PT = True
except ImportError:  # pragma: no cover - exercised only where it is absent
    HAVE_PT = False

COUNCIL, SERIAL, ASK = "council", "serial", "ask"

RESET = "\x1b[0m"
BAR = "\x1b[48;5;236m"
MODE_COUNCIL = "\x1b[1;38;5;39m"
MODE_SERIAL = "\x1b[1;38;5;215m"
MODE_ASK = "\x1b[1;38;5;150m"
KEY = "\x1b[38;5;245m"
VALUE = "\x1b[38;5;252m"
WARN = "\x1b[38;5;209m"
OK = "\x1b[38;5;108m"


def short_model(model: str) -> str:
    """Drop the vendor prefix. `claude-opus-5` is opus-5 everywhere it is shown,
    because the provider is already visible from the letter and the roster."""
    for prefix in ("claude-", "gemini-"):
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def humanise(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.0f}k"
    return str(count)


@dataclass
class MemberLine:
    """One member, compressed to the few numbers worth glancing at."""

    anon: str
    name: str
    context: int
    window: int | None
    turns: int

    def render(self) -> str:
        ctx = humanise(self.context) if self.context else "-"
        if self.context and self.window:
            share = self.context / self.window
            colour = WARN if share > 0.7 else OK
            ctx = f"{colour}{ctx}/{humanise(self.window)}{RESET}"
        else:
            ctx = f"{VALUE}{ctx}{RESET}"
        return f"{KEY}{self.anon[-1]}{RESET} {self.name} {ctx} {KEY}t{self.turns}{RESET}"


@dataclass
class Status:
    """What the bar shows. Assembled fresh on every redraw."""

    mode: str
    slug: str
    where: str
    rounds: int
    secretary_context: int
    secretary_window: int | None
    cost_usd: float
    calls: dict[str, int]
    members: list[MemberLine]
    dismissed: bool = False

    def _mode_cell(self) -> str:
        if self.dismissed:
            return f"{MODE_SERIAL}SOLO{RESET}"
        colour = MODE_COUNCIL if self.mode == COUNCIL else MODE_SERIAL
        return f"{colour}{self.mode.upper()}{RESET}"

    def _quota_cell(self) -> str:
        # No provider exposes a real quota, so this stays what can actually be
        # measured: claude's reported cost, and a call count for the others.
        # agy is named because its quota is the scarce one.
        bits = []
        if self.cost_usd:
            bits.append(f"{KEY}${RESET}{VALUE}{self.cost_usd:.2f}{RESET}")
        for provider in ("agy", "codex", "claude"):
            count = self.calls.get(provider)
            if count:
                colour = WARN if provider == "agy" else KEY
                bits.append(f"{colour}{provider}{RESET}{VALUE}{count}{RESET}")
        return " ".join(bits) or f"{KEY}no calls yet{RESET}"

    def lines(self) -> list[str]:
        ctx = humanise(self.secretary_context) if self.secretary_context else "-"
        if self.secretary_context and self.secretary_window:
            ctx = f"{ctx}/{humanise(self.secretary_window)}"
        first = (
            f" {self._mode_cell()} "
            f"{KEY}·{RESET} {VALUE}{self.slug}{RESET} "
            f"{KEY}·{RESET} {VALUE}{self.where}{RESET} "
            f"{KEY}·{RESET} {KEY}r{RESET}{VALUE}{self.rounds}{RESET} "
            f"{KEY}·{RESET} {KEY}sec{RESET} {VALUE}{ctx}{RESET} "
            f"{KEY}·{RESET} {self._quota_cell()}"
        )
        second = "   " + "  ".join(m.render() for m in self.members) if self.members else ""
        return [first] + ([second] if second else [])

    def render(self) -> str:
        return "\n".join(f"{BAR}{line}{RESET}" for line in self.lines())


class Shell:
    """Reads lines, toggles mode on Tab, and keeps the bar current."""

    def __init__(self, status: Callable[[str], Status], toggle: Callable[[str], str]) -> None:
        self.status = status
        self.toggle = toggle
        self.mode = COUNCIL
        self.session = None
        if HAVE_PT and sys.stdin.isatty():
            keys = KeyBindings()

            @keys.add("tab")
            def _(event: object) -> None:
                # Tab is the mode switch, not completion; there is nothing to
                # complete here and the switch is the gesture used constantly.
                self.mode = self.toggle(self.mode)
                app = getattr(event, "app", None)
                if app is not None:
                    app.invalidate()

            self.session = PromptSession(key_bindings=keys)

    def prompt(self) -> str:
        colour = MODE_COUNCIL if self.mode == COUNCIL else MODE_SERIAL
        text = f"\n{colour}{self.mode}{RESET}> "
        if self.session is None:
            return input(text)
        return self.session.prompt(
            ANSI(text),
            bottom_toolbar=lambda: ANSI(self.status(self.mode).render()),
            refresh_interval=1.0,
        )


def ask_prompt(where: str) -> str:
    """Read the first question.

    It is typed here rather than passed on the command line, so that starting a
    council is one keystroke and the question gets the same line editing as
    every later turn. There is no council yet, so the bar can only show the mode
    and where we are: no slug, no rounds, no usage.
    """
    text = f"\n{MODE_ASK}{ASK}{RESET}> "
    if not (HAVE_PT and sys.stdin.isatty()):
        return input(f"\n{ASK}> ")
    bar = (
        f"{BAR} {MODE_ASK}ASK{RESET} "
        f"{KEY}\u00b7{RESET} {VALUE}{where}{RESET} "
        f"{KEY}\u00b7{RESET} {KEY}the secretary gathers first, then the members answer{RESET}"
    )
    return PromptSession().prompt(ANSI(text), bottom_toolbar=lambda: ANSI(f"{BAR}{bar}{RESET}"))
