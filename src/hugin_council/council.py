"""Orchestration: gather, broadcast, synthesise, and the serial side channel.

The secretary holds two sessions. The council one gathers and synthesises and
writes only the archive; the serial one is a general assistant that does the
arbitrary work. They are split because the roles have incompatible standing
instructions: council is defined by may-not-resolve, serial exists to answer.
One session would assert and suspend that constraint on every tab.
"""

from __future__ import annotations

import string
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from hugin.prompts import resolve_prompt
from hugin.session import Session, SessionError, parse_spec

from . import archive as arc
from .config import CouncilConfig
from .context import WorkContext
from .status import StatusLine
from .tui import short_model

PROMPT_DIR = Path(__file__).parent / "prompts"

SECRETARY_COUNCIL = "secretary-council"
SECRETARY_SERIAL = "secretary-serial"


def anon_labels(count: int) -> list[str]:
    """Participant A, B, C. Model names trigger priors about who is credible,
    and letters still let a position be followed across rounds."""
    return [f"Participant {c}" for c in string.ascii_uppercase[:count]]


def fill(template: str, **values: str) -> str:
    """Substitute ``{{TOKEN}}`` placeholders.

    Not str.format: the prompt bodies are prose full of braces and backticks.
    """
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    return out


@dataclass
class MemberAnswer:
    label: str
    anon: str
    text: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


@dataclass
class Council:
    cfg: CouncilConfig
    ctx: WorkContext
    archive: arc.Archive
    members: list[Session] = field(default_factory=list)
    secretary_spec: str = ""
    on_note: Callable[[str], None] | None = None

    # ------------------------------------------------------------------ plumbing

    def note(self, text: str) -> None:
        if self.on_note:
            self.on_note(text)

    def _prompt(self, base: str, explicit: Path | None) -> str:
        path = resolve_prompt(base, self.cfg.language, explicit, PROMPT_DIR)
        text = path.read_text(encoding="utf-8")
        return text.replace("{{LANGUAGE}}", self.cfg.language_name)

    def _session(self, spec: str, *, read_only: bool, key: str | None = None) -> Session:
        stored = self.archive.get_session(key) if key else None
        if stored:
            return Session.from_dict(stored, cfg=self.cfg.llm)
        return parse_spec(
            spec,
            self.ctx.primary,
            cfg=self.cfg.llm,
            read_only=read_only,
            extra_dirs=list(self.ctx.extra),
        )

    def _remember(self, key: str, session: Session) -> None:
        self.archive.put_session(key, session.to_dict())

    # ------------------------------------------------------------------- roster

    def attach(self, specs: list[str], secretary_spec: str) -> None:
        """Create or reattach the member sessions and record the roster."""
        self.secretary_spec = secretary_spec
        stored = self.archive.state.get("roster")
        if stored:
            specs = list(stored)
        else:
            self.archive.state["roster"] = list(specs)
            self.archive.state["secretary"] = secretary_spec
            self.archive.save()
        self.members = [
            self._session(spec, read_only=True, key=f"member-{index}")
            for index, spec in enumerate(specs)
        ]

    @property
    def anon_map(self) -> dict[str, str]:
        return {
            session.label: anon
            for session, anon in zip(self.members, anon_labels(len(self.members)))
        }

    # ------------------------------------------------------------------ phase 1

    def gather(self) -> str:
        existing = self.archive.brief
        if existing:
            return existing
        prompt = fill(
            self._prompt("gather", self.cfg.gather_prompt_path),
            QUESTION=self.archive.question,
            CONTEXT=self.ctx.describe(),
        )
        secretary = self._session(self.secretary_spec, read_only=False, key=SECRETARY_COUNCIL)
        with StatusLine() as status:
            status.start("gathering")
            try:
                turn = secretary.send(prompt, timeout=self.cfg.turn_timeout)
            except SessionError as exc:
                status.failed("gathering", str(exc)[:60])
                raise
            status.done("gathering")
        self._remember(SECRETARY_COUNCIL, secretary)
        self.archive.write(arc.BRIEF_FILE, turn.text + "\n")
        return turn.text

    # ------------------------------------------------------------------ phase 2

    def _member_prompt(self, turn: str, brief: str | None, synthesis: str | None) -> str:
        if synthesis is None:
            brief_block = f"## Background gathered for you\n\n{brief}" if brief else ""
            # The turn is usually the question verbatim in round one, but not
            # when something was promoted from the serial channel first, and
            # dropping that would lose it silently.
            extra = turn.strip()
            turn_block = (
                f"## Also from the user\n\n{extra}"
                if extra and extra != self.archive.question.strip()
                else ""
            )
            return fill(
                self._prompt("members", self.cfg.members_prompt_path),
                MEMBER_COUNT=str(len(self.members)),
                CONTEXT=self.ctx.describe(),
                QUESTION=self.archive.question,
                BRIEF=brief_block,
                TURN=turn_block,
            )
        return fill(
            self._prompt("members_followup", self.cfg.members_prompt_path),
            SYNTHESIS=synthesis,
            TURN=turn,
        )

    def broadcast(self, turn: str) -> tuple[Path, list[MemberAnswer]]:
        synthesis = self.archive.latest_synthesis()
        prompt = self._member_prompt(turn, self.archive.brief, synthesis)
        round_dir = self.archive.open_round()
        (round_dir / arc.MEMBER_PROMPT).write_text(prompt, encoding="utf-8")

        anon = self.anon_map
        answers: list[MemberAnswer | None] = [None] * len(self.members)

        with StatusLine() as status:
            for session in self.members:
                # The same letter and short name the synthesis and the status bar
                # use, so a slow row is identifiable as "the one that is B".
                status.add(session.label, f"{anon[session.label]} {short_model(session.model)}")

            def run(index: int) -> None:
                session = self.members[index]
                status.start(session.label)
                try:
                    result = session.send(prompt, timeout=self.cfg.turn_timeout)
                except SessionError as exc:
                    answers[index] = MemberAnswer(
                        label=session.label, anon=anon[session.label], text="", error=str(exc)
                    )
                    status.failed(session.label, str(exc).splitlines()[0][:60])
                    return
                answers[index] = MemberAnswer(
                    label=session.label, anon=anon[session.label], text=result.text
                )
                words = len(result.text.split())
                status.done(session.label, f"{words} words")

            with ThreadPoolExecutor(max_workers=max(len(self.members), 1)) as pool:
                list(pool.map(run, range(len(self.members))))

        collected = [a for a in answers if a is not None]
        for index, answer in enumerate(collected):
            self._remember(f"member-{index}", self.members[index])
            body = answer.text if answer.ok else f"(failed: {answer.error})"
            (round_dir / arc.answer_filename(answer.label)).write_text(
                f"<!-- {answer.anon} = {answer.label} -->\n\n{body}\n", encoding="utf-8"
            )
        return round_dir, collected

    # ----------------------------------------------------------------- phase 2b

    def synthesise(self, round_dir: Path, answers: list[MemberAnswer], turn: str) -> str:
        usable = [a for a in answers if a.ok]
        if not usable:
            raise SessionError("no member answered, nothing to synthesise")
        blocks = "\n\n".join(f"### {a.anon}\n\n{a.text.strip()}" for a in usable)
        previous = self.archive.latest_synthesis()
        prompt = fill(
            self._prompt("synthesis", self.cfg.synthesis_prompt_path),
            MEMBER_COUNT=str(len(usable)),
            QUESTION=self.archive.question,
            TURN=f"## The user's latest turn\n\n{turn}" if turn.strip() else "",
            ANSWERS=blocks,
            PREVIOUS=(
                f"## The map so far, whose numbering you must keep\n\n{previous}"
                if previous
                else ""
            ),
        )
        (round_dir / arc.SECRETARY_PROMPT).write_text(prompt, encoding="utf-8")

        secretary = self._session(self.secretary_spec, read_only=False, key=SECRETARY_COUNCIL)
        with StatusLine() as status:
            status.start("synthesising")
            try:
                result = secretary.send(prompt, timeout=self.cfg.turn_timeout)
            except SessionError as exc:
                status.failed("synthesising", str(exc)[:60])
                raise
            status.done("synthesising")
        self._remember(SECRETARY_COUNCIL, secretary)
        (round_dir / arc.SYNTHESIS).write_text(result.text + "\n", encoding="utf-8")
        return result.text

    def round(self, turn: str) -> str:
        carried = self.take_promoted()
        if carried:
            turn = f"{carried}\n\n---\n\n{turn}"
        round_dir, answers = self.broadcast(turn)
        failed = [a.label for a in answers if not a.ok]
        if failed:
            self.note(f"no answer from: {', '.join(failed)}")
        return self.synthesise(round_dir, answers, turn)

    # ------------------------------------------------------------------- serial

    def serial(self, text: str) -> str:
        """The side channel. Never reaches the members."""
        session = self._session(self.secretary_spec, read_only=False, key=SECRETARY_SERIAL)
        if session.turns == 0:
            brief = self.archive.brief
            synthesis = self.archive.latest_synthesis()
            seed = fill(
                self._prompt("serial", self.cfg.serial_prompt_path),
                QUESTION=self.archive.question,
                BRIEF=f"Brief:\n\n{brief}" if brief else "",
                SYNTHESIS=f"Latest synthesis:\n\n{synthesis}" if synthesis else "",
                CONTEXT=self.ctx.describe(),
            )
            text = f"{seed}\n\n---\n\n{text}"
        else:
            synthesis = self.archive.latest_synthesis()
            seen = self.archive.state.get("serial_synthesis_rounds")
            if synthesis and seen != self.archive.rounds:
                text = (
                    "The council has moved on. Latest synthesis:\n\n"
                    f"{synthesis}\n\n---\n\n{text}"
                )
        result = session.send(text, timeout=self.cfg.turn_timeout)
        self._remember(SECRETARY_SERIAL, session)
        self.archive.state["serial_synthesis_rounds"] = self.archive.rounds
        self.archive.save()
        return result.text

    # --------------------------------------------------------------------- solo

    def solo(self, outcome: str) -> None:
        """Dismiss the members for good and record which option was taken.

        No transition turn is needed: the serial session was never under the
        may-not-resolve constraint, so there is no restraint to lift.
        """
        self.archive.state["dismissed"] = True
        self.archive.save()
        existing = self.archive.read(arc.OUTCOME_FILE) or ""
        self.archive.write(
            arc.OUTCOME_FILE,
            (existing + f"\n{outcome.strip()}\n" if existing else outcome.strip() + "\n"),
        )

    # ------------------------------------------------------------------ numbers

    def session_states(self) -> dict[str, dict]:
        """Persisted per-session counts, for the status bar.

        Read from the archive rather than from live objects because the
        secretary's two sessions are created per job and not held open.
        """
        return dict(self.archive.sessions())

    def calls_by_provider(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for state in self.session_states().values():
            provider = str(state.get("provider") or "?")
            counts[provider] = counts.get(provider, 0) + int(state.get("turns") or 0)
        return counts

    def total_cost_usd(self) -> float:
        """Partial by construction: only claude reports a per-turn cost."""
        return sum(
            float(state.get("total_cost_usd") or 0.0)
            for state in self.session_states().values()
        )

    @property
    def dismissed(self) -> bool:
        return bool(self.archive.state.get("dismissed"))

    def promote(self, text: str) -> None:
        """Carry something from the serial channel into the next broadcast.

        A door, not a leak: nothing crosses unless it is named here.
        """
        pending = self.archive.state.setdefault("promoted", [])
        pending.append(text)
        self.archive.save()

    def take_promoted(self) -> str:
        pending = self.archive.state.get("promoted") or []
        if not pending:
            return ""
        self.archive.state["promoted"] = []
        self.archive.save()
        joined = "\n\n".join(pending)
        return f"Carried over from a side conversation with the user:\n\n{joined}"
