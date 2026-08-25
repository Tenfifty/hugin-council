"""The council on disk.

Everything is markdown except ``sessions.json``, which is machine state
(provider, model, effort, session id) rather than content. Structuring the state
is a different thing from structuring the synthesis, which stays prose on
purpose: see "The map is prose. The archive is the structure." in the README.

Nothing is ever overwritten. Each round gets its own directory, so a later pass
can see what was cut between rounds and not just what survived.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

SESSIONS_FILE = "sessions.json"
QUESTION_FILE = "question.md"
BRIEF_FILE = "brief.md"
OUTCOME_FILE = "outcome.md"

MEMBER_PROMPT = "prompt-members.md"
SECRETARY_PROMPT = "prompt-secretary.md"
SYNTHESIS = "synthesis.md"


def slugify(text: str, words: int = 6) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    parts = cleaned.split()[:words]
    slug = "-".join(parts).strip("-")
    return slug or "council"


def answer_filename(label: str) -> str:
    return f"answer-{label.replace(':', '-').replace('/', '-')}.md"


@dataclass
class Archive:
    """A single council directory."""

    root: Path
    state: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------------- lifecycle

    @classmethod
    def create(cls, state_dir: Path, question: str, today: date | None = None) -> "Archive":
        stamp = (today or date.today()).isoformat()
        base = f"{stamp}-{slugify(question)}"
        root = state_dir / base
        suffix = 2
        while root.exists():
            root = state_dir / f"{base}-{suffix}"
            suffix += 1
        root.mkdir(parents=True)
        archive = cls(root=root, state={"question": question, "created": stamp, "rounds": 0})
        archive.write(QUESTION_FILE, question.strip() + "\n")
        archive.save()
        return archive

    @classmethod
    def load(cls, root: Path) -> "Archive":
        root = Path(root)
        path = root / SESSIONS_FILE
        if not path.exists():
            raise FileNotFoundError(f"no council at {root} (missing {SESSIONS_FILE})")
        return cls(root=root, state=json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def find_all(state_dir: Path) -> list[Path]:
        if not state_dir.exists():
            return []
        found = [p for p in state_dir.iterdir() if (p / SESSIONS_FILE).exists()]
        return sorted(found, key=lambda p: (p / SESSIONS_FILE).stat().st_mtime, reverse=True)

    @classmethod
    def latest(cls, state_dir: Path) -> "Archive":
        found = cls.find_all(state_dir)
        if not found:
            raise FileNotFoundError(f"no councils under {state_dir}")
        return cls.load(found[0])

    def save(self) -> None:
        self.write(SESSIONS_FILE, json.dumps(self.state, indent=2, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------- fields

    @property
    def question(self) -> str:
        return str(self.state.get("question") or "")

    @property
    def rounds(self) -> int:
        return int(self.state.get("rounds") or 0)

    @property
    def slug(self) -> str:
        return self.root.name

    def round_dir(self, number: int) -> Path:
        return self.root / f"round-{number:02d}"

    def open_round(self) -> Path:
        number = self.rounds + 1
        path = self.round_dir(number)
        path.mkdir(parents=True, exist_ok=True)
        self.state["rounds"] = number
        self.save()
        return path

    # -------------------------------------------------------------------- files

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, name: str) -> str | None:
        path = self.root / name
        return path.read_text(encoding="utf-8") if path.exists() else None

    @property
    def brief(self) -> str | None:
        return self.read(BRIEF_FILE)

    def latest_synthesis(self) -> str | None:
        for number in range(self.rounds, 0, -1):
            text = self.read(f"{self.round_dir(number).name}/{SYNTHESIS}")
            if text:
                return text
        return None

    # ----------------------------------------------------------------- sessions

    def sessions(self) -> dict[str, Any]:
        return self.state.setdefault("sessions", {})

    def put_session(self, key: str, data: dict[str, Any]) -> None:
        self.sessions()[key] = data
        self.save()

    def get_session(self, key: str) -> dict[str, Any] | None:
        return self.sessions().get(key)
