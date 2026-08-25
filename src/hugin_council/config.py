"""Council config: ``hugin.yaml`` + ``council.yaml``, deep-merged.

Rosters and the secretary are ``provider[:model[:effort]]`` strings, the same
grammar CLI flags use, so a flag and a YAML entry parse identically through
``hugin.session.parse_spec``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugin.config import SharedConfig, load_tool
from hugin.llm import LLMConfig

DEFAULT_SECRETARY = "claude:claude-opus-5:high"
# fable-5 is out of every roster until the account is upgraded (2026-08-25).
# It works, so this is a quota decision, not a capability one: put the two
# commented lines back and delete this comment when the upgrade lands.
DEFAULT_ROSTERS: dict[str, list[str]] = {
    "default": [
        "claude:claude-opus-5:high",
        # "claude:claude-fable-5:high",
        "codex:gpt-5.6-sol:high",
    ],
    # agy lives here and nowhere else: the quota is the scarce resource, so it
    # gets spent only when breadth is asked for explicitly.
    "wide": [
        "claude:claude-opus-5:high",
        "codex:gpt-5.6-sol:high",
        "codex:gpt-5.5:xhigh",
        "agy:gemini-3.1-pro-high",
        "agy:gemini-3.7-flash-high",
    ],
    "cheap": [
        # haiku takes fable's place as the claude voice here. It is a smaller
        # model rather than an older one, so the pairing is no longer
        # same-brand-different-generation; that returns with fable.
        "claude:claude-haiku-4-5-20251001:medium",
        "codex:gpt-5.4-mini:medium",
    ],
}
LANGUAGE_NAMES = {"sv": "Swedish", "en": "English"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Synthesis is clustering and compression, not the hard reasoning; the hard
# reasoning is the members'. Measured 2026-08-25: effort is part of the
# server-side cache key for both claude and codex, so the step down costs one
# full re-read of the secretary's conversation and every synthesis after it hits
# the cache again. Once per council, not once per round. Set to "high" to undo.
DEFAULT_SYNTHESIS_EFFORT = "medium"


@dataclass
class CouncilConfig(SharedConfig):
    """Everything the tool reads from disk."""

    secretary: str = DEFAULT_SECRETARY
    rosters: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_ROSTERS))
    roster: str = "default"
    # State, not output: safe to wipe. See CONVENTIONS.md.
    state_dir: Path = Path("~/.council").expanduser()
    # Root under which a cwd counts as "a project repo".
    projects_root: Path = Path("~/projs").expanduser()
    # The general Hugin directories, always in reach. Defaults to the vault,
    # which is where AGENTS.md and instructions/ live.
    hugin_dirs: list[Path] = field(default_factory=list)
    # Effort for phase 2b only. None means "whatever the secretary spec says".
    synthesis_effort: str | None = DEFAULT_SYNTHESIS_EFFORT
    turn_timeout: int = 1800
    llm: LLMConfig = field(default_factory=LLMConfig)
    gather_prompt_path: Path | None = None
    members_prompt_path: Path | None = None
    synthesis_prompt_path: Path | None = None
    serial_prompt_path: Path | None = None

    @property
    def language_name(self) -> str:
        return LANGUAGE_NAMES.get(self.language, self.language)

    def roster_specs(self, name: str | None = None) -> list[str]:
        key = name or self.roster
        if key not in self.rosters:
            known = ", ".join(sorted(self.rosters)) or "none configured"
            raise ValueError(f"unknown roster {key!r}; known: {known}")
        specs = self.rosters[key]
        if not specs:
            raise ValueError(f"roster {key!r} is empty")
        return list(specs)


def _paths(value: Any) -> list[Path]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return [Path(str(v)).expanduser() for v in value]


def build(merged: dict[str, Any]) -> CouncilConfig:
    shared = SharedConfig.fields_from_merged(merged)
    data = merged.get("council") or {}

    rosters = data.get("rosters") or merged.get("rosters") or DEFAULT_ROSTERS
    if not isinstance(rosters, dict):
        raise ValueError("council.rosters must be a mapping of name -> list")
    rosters = {str(k): [str(s) for s in (v or [])] for k, v in rosters.items()}

    hugin_dirs = _paths(data.get("hugin_dirs"))
    if not hugin_dirs:
        vault = shared.get("vault_path")
        # Only the vault. Reaching for its parent would pull in the whole of
        # ~/Documents on a setup where vault_path is already the top level.
        hugin_dirs = [Path(vault)] if vault else []

    state_dir = data.get("state_dir")
    projects_root = data.get("projects_root")
    return CouncilConfig(
        **shared,
        secretary=str(data.get("secretary") or merged.get("secretary") or DEFAULT_SECRETARY),
        rosters=rosters,
        roster=str(data.get("roster") or "default"),
        state_dir=Path(state_dir).expanduser() if state_dir else CouncilConfig.state_dir,
        projects_root=(
            Path(projects_root).expanduser() if projects_root else CouncilConfig.projects_root
        ),
        hugin_dirs=hugin_dirs,
        synthesis_effort=_effort(data.get("synthesis_effort", DEFAULT_SYNTHESIS_EFFORT)),
        turn_timeout=int(data.get("turn_timeout") or 1800),
        llm=LLMConfig.from_dict(merged.get("llm") or {}),
        gather_prompt_path=_opt(data.get("gather_prompt_path")),
        members_prompt_path=_opt(data.get("members_prompt_path")),
        synthesis_prompt_path=_opt(data.get("synthesis_prompt_path")),
        serial_prompt_path=_opt(data.get("serial_prompt_path")),
    )


def _effort(value: Any) -> str | None:
    if value is None or value == "":
        return None
    effort = str(value).lower()
    if effort not in EFFORTS:
        raise ValueError(f"synthesis_effort must be one of: {', '.join(EFFORTS)}")
    return effort


def _opt(value: Any) -> Path | None:
    return Path(str(value)).expanduser() if value else None


def load() -> CouncilConfig:
    return load_tool("council", build)
