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

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable

try:  # prompt_toolkit is a soft dependency
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings

    HAVE_PT = True
except ImportError:  # pragma: no cover - exercised only where it is absent
    HAVE_PT = False

COUNCIL, SERIAL, ASK = "council", "serial", "ask"

# What Tab completes, when the line is a slash command and nothing else yet.
# Aliases (/c, /s, /q) are left out: nobody needs help typing one letter.
COMMANDS = (
    "/answer",
    "/answers",
    "/brief",
    "/council",
    "/edit",
    "/help",
    "/map",
    "/promote",
    "/quit",
    "/serial",
    "/solo",
    "/status",
)


def complete_command(text: str, commands: tuple[str, ...] = COMMANDS) -> list[str]:
    """Commands that ``text`` is a prefix of, if it is a lone slash word."""
    if not text.startswith("/") or " " in text or "\n" in text:
        return []
    return [c for c in commands if c.startswith(text)]

RESET = "\x1b[0m"
BAR = "\x1b[48;5;236m"
MODE_COUNCIL = "\x1b[1;38;5;39m"
MODE_SERIAL = "\x1b[1;38;5;215m"
MODE_ASK = "\x1b[1;38;5;150m"
KEY = "\x1b[38;5;245m"
VALUE = "\x1b[38;5;252m"
WARN = "\x1b[38;5;209m"
OK = "\x1b[38;5;108m"


DIM = "\x1b[38;5;242m"
TOOL = "\x1b[38;5;109m"


def event_line(kind: str, name: str, detail: str, colour: bool = True) -> str:
    """One line for one thing the secretary did.

    Always one line. A gather turn makes dozens of these, and a `cat` of a long
    file wrapping over the terminal would bury the sequence, which is the part
    worth seeing.
    """
    detail = " ".join(detail.split())
    if kind == "notice":
        head, body = f"! {name}", detail
    elif kind == "tool":
        head, body = f"· {name}", detail
    else:
        head, body = "·", detail
    width = max(shutil.get_terminal_size((100, 24)).columns - 4, 40)
    room = width - len(head) - 2
    if len(body) > room:
        body = body[: max(room - 1, 0)] + "…"
    if not colour:
        return f"  {head}  {body}".rstrip()
    tint = WARN if kind == "notice" else TOOL if kind == "tool" else DIM
    return f"  {tint}{head}{RESET}  {DIM}{body}{RESET}".rstrip()


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
    read: int
    turns: int

    def render(self) -> str:
        read = f"{VALUE}{humanise(self.read) if self.read else '-'}{RESET}"
        return f"{KEY}{self.anon[-1]}{RESET} {self.name} {read} {KEY}t{self.turns}{RESET}"


@dataclass
class Status:
    """What the bar shows. Assembled fresh on every redraw."""

    mode: str
    slug: str
    where: str
    rounds: int
    secretary_read: int
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
        # Tokens read on the last turn, not context use. The providers sum usage
        # over every request a turn makes, so an agentic turn reads many times
        # its own context and no honest denominator exists. See hugin.session.
        read = humanise(self.secretary_read) if self.secretary_read else "-"
        first = (
            f" {self._mode_cell()} "
            f"{KEY}·{RESET} {VALUE}{self.slug}{RESET} "
            f"{KEY}·{RESET} {VALUE}{self.where}{RESET} "
            f"{KEY}·{RESET} {KEY}r{RESET}{VALUE}{self.rounds}{RESET} "
            f"{KEY}·{RESET} {KEY}sec read{RESET} {VALUE}{read}{RESET} "
            f"{KEY}·{RESET} {self._quota_cell()}"
        )
        second = "   " + "  ".join(m.render() for m in self.members) if self.members else ""
        return [first] + ([second] if second else [])

    def render(self) -> str:
        return "\n".join(f"{BAR}{line}{RESET}" for line in self.lines())


def _interactive() -> bool:
    return HAVE_PT and sys.stdin.isatty()


def _bindings() -> "KeyBindings":
    """Enter sends; Alt-Enter and Ctrl-J insert a newline.

    A council question is often several paragraphs, so the buffer is multiline
    and Enter is rebound to accept. Alt-Enter arrives as Escape then Enter and
    some terminals swallow it, which is why Ctrl-J (a bare line feed, which no
    terminal interprets) is there as the fallback that Claude Code and Codex
    also use. Shift-Enter sends nothing distinguishable in most terminals and
    is not bound. Pasted text keeps its newlines regardless, through bracketed
    paste.
    """
    keys = KeyBindings()

    @keys.add("enter")
    def _accept(event: object) -> None:
        event.current_buffer.validate_and_handle()  # type: ignore[attr-defined]

    @keys.add("escape", "enter")
    @keys.add("c-j")
    def _newline(event: object) -> None:
        event.current_buffer.newline()  # type: ignore[attr-defined]

    return keys


def _continuation(width: int, line_number: int, is_soft_wrap: bool) -> str:
    return " " * width


if HAVE_PT:

    class _CommandCompleter(Completer):
        def get_completions(self, document, complete_event):  # type: ignore[override]
            word = document.text_before_cursor
            for command in complete_command(word):
                yield Completion(command, start_position=-len(word))


def _session(keys: "KeyBindings") -> "PromptSession":
    return PromptSession(
        key_bindings=keys,
        multiline=True,
        prompt_continuation=_continuation,
        completer=_CommandCompleter(),
        complete_while_typing=False,
    )


class Shell:
    """Reads lines, toggles mode on Tab, and keeps the bar current."""

    def __init__(self, status: Callable[[str], Status], toggle: Callable[[str], str]) -> None:
        self.status = status
        self.toggle = toggle
        self.mode = COUNCIL
        self.session = None
        if _interactive():
            keys = _bindings()

            @keys.add("tab")
            def _(event: object) -> None:
                # Tab is the mode switch, the gesture used constantly. The one
                # exception is a half-typed slash command, where it completes:
                # a lone "/an" is never meant as a turn to anyone.
                buffer = event.current_buffer  # type: ignore[attr-defined]
                if complete_command(buffer.text):
                    if buffer.complete_state:
                        buffer.complete_next()
                    else:
                        buffer.start_completion(select_first=True)
                    return
                self.mode = self.toggle(self.mode)
                app = getattr(event, "app", None)
                if app is not None:
                    app.invalidate()

            self.session = _session(keys)

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


def edit_text(initial: str = "", editor: str | None = None) -> str:
    """Hand a turn to $VISUAL or $EDITOR and return what came back.

    For the turn that is too long for a prompt even with newlines. The file is
    markdown so the editor highlights it, and a turn left empty means "never
    mind" rather than an empty broadcast.
    """
    command = editor or os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    with tempfile.NamedTemporaryFile("w+", suffix=".md", encoding="utf-8", delete=False) as handle:
        handle.write(initial)
        path = handle.name
    try:
        subprocess.call([*command.split(), path])
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def notify(text: str, stream=None) -> None:
    """Say that a long wait is over, to someone who has looked away.

    A bell in the terminal, which most emulators turn into a taskbar flag, and
    a desktop notification when there is a desktop and notify-send to reach it.
    Nothing is raised: a notification that fails is not worth a message.
    """
    out = stream or sys.stdout
    if getattr(out, "isatty", lambda: False)():
        out.write("\a")
        out.flush()
    if shutil.which("notify-send") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        try:
            subprocess.Popen(
                ["notify-send", "--app-name=hugin-council", "hugin-council", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def ask_prompt(where: str) -> str:
    """Read the first question.

    It is typed here rather than passed on the command line, so that starting a
    council is one keystroke and the question gets the same line editing as
    every later turn. There is no council yet, so the bar can only show the mode
    and where we are: no slug, no rounds, no usage.
    """
    text = f"\n{MODE_ASK}{ASK}{RESET}> "
    if not _interactive():
        return input(f"\n{ASK}> ")
    bar = (
        f"{BAR} {MODE_ASK}ASK{RESET} "
        f"{KEY}\u00b7{RESET} {VALUE}{where}{RESET} "
        f"{KEY}\u00b7{RESET} {KEY}Alt-Enter for a new line; the secretary gathers first{RESET}"
    )
    return _session(_bindings()).prompt(
        ANSI(text), bottom_toolbar=lambda: ANSI(f"{BAR}{bar}{RESET}")
    )
