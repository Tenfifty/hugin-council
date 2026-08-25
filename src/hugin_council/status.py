"""One line per member: who is still thinking, for how long, who died.

Deliberately the whole of the UI. During a round the only thing worth showing is
progress; the map itself reads better as plain text afterwards.

Members are asked in parallel, so the interesting question during a round is not
"how long has this taken" but "who is left". Hence a footer that names who is
still out, and a wall clock for the round rather than only per member: the round
costs the slowest member, not the sum.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import TextIO

SPINNER = "|/-\\"


@dataclass
class _Row:
    label: str
    display: str = ""
    state: str = "waiting"
    started: float | None = None
    finished: float | None = None
    note: str = ""

    def elapsed(self) -> float:
        if self.started is None:
            return 0.0
        return (self.finished or time.monotonic()) - self.started

    @property
    def name(self) -> str:
        return self.display or self.label


@dataclass
class StatusLine:
    """Redraws in place on a tty, prints one line per event otherwise."""

    stream: TextIO = field(default_factory=lambda: sys.stderr)
    interval: float = 0.2
    rows: dict[str, _Row] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _drawn: int = 0
    _tick: int = 0
    _t0: float | None = None

    @property
    def tty(self) -> bool:
        return bool(getattr(self.stream, "isatty", lambda: False)())

    def add(self, label: str, display: str = "") -> None:
        with self._lock:
            self.rows[label] = _Row(label=label, display=display)

    def start(self, label: str, display: str = "") -> None:
        with self._lock:
            row = self.rows.setdefault(label, _Row(label=label))
            if display:
                row.display = display
            row.state = "thinking"
            row.started = time.monotonic()
            if self._t0 is None:
                self._t0 = row.started
        if not self.tty:
            self._plain(f"{self.rows[label].name}: thinking")

    def done(self, label: str, note: str = "") -> None:
        self._finish(label, "done", note)

    def failed(self, label: str, note: str = "") -> None:
        self._finish(label, "failed", note)

    def _finish(self, label: str, state: str, note: str) -> None:
        with self._lock:
            row = self.rows.setdefault(label, _Row(label=label))
            row.state = state
            row.finished = time.monotonic()
            row.note = note
        if not self.tty:
            row = self.rows[label]
            self._plain(f"{row.name}: {state} in {row.elapsed():.0f}s {note}".rstrip())

    def _plain(self, text: str) -> None:
        self.stream.write(text + "\n")
        self.stream.flush()

    # ------------------------------------------------------------------ drawing

    def __enter__(self) -> "StatusLine":
        if self.tty:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self.tty:
            self._draw(final=True)
        else:
            summary = self._summary(list(self.rows.values()))
            if summary:
                self._plain(summary.strip())

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self._draw()

    def _wall(self, rows: list[_Row]) -> float:
        """Wall clock for the round, not the sum of the members."""
        if self._t0 is None:
            return 0.0
        if any(row.state == "thinking" for row in rows):
            return time.monotonic() - self._t0
        finished = [row.finished for row in rows if row.finished is not None]
        return max(finished) - self._t0 if finished else 0.0

    def _summary(self, rows: list[_Row]) -> str | None:
        # One row is its own summary; naming who is left only helps from two up.
        if len(rows) < 2:
            return None
        thinking = [row for row in rows if row.state == "thinking"]
        done = sum(1 for row in rows if row.state == "done")
        failed = sum(1 for row in rows if row.state == "failed")
        # A failure is not an answer, so it is counted apart rather than folded
        # into the numerator, which would read as success.
        tail = f", {failed} failed" if failed else ""
        wall = self._wall(rows)
        if thinking:
            waiting = ", ".join(row.name for row in thinking)
            return f"   {done}/{len(rows)} answered{tail}, waiting on {waiting}   {wall:.0f}s"
        return f"   {done}/{len(rows)} answered in {wall:.0f}s{tail}"

    def _draw(self, final: bool = False) -> None:
        with self._lock:
            rows = list(self.rows.values())
        self._tick += 1
        spin = SPINNER[self._tick % len(SPINNER)]
        lines = []
        for row in rows:
            if row.state == "thinking":
                mark = spin
            elif row.state == "done":
                mark = "+"
            elif row.state == "failed":
                mark = "!"
            else:
                mark = " "
            note = f"  {row.note}" if row.note else ""
            clock = f"{row.elapsed():5.0f}s" if row.started is not None else "     -"
            lines.append(f" {mark} {row.name:<28} {clock}{note}")
        summary = self._summary(rows)
        if summary:
            lines.append(summary)
        out = []
        if self._drawn:
            out.append(f"\x1b[{self._drawn}A")
        for line in lines:
            out.append("\x1b[2K" + line + "\n")
        self.stream.write("".join(out))
        self.stream.flush()
        self._drawn = 0 if final else len(lines)
