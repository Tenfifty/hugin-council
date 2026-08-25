"""Where the council looks, given where it was launched.

The command runs from anywhere. Two cases:

* Inside a subdirectory of ``projects_root`` (``~/projs`` by default): that repo
  is the primary directory and the general Hugin directories come along, so a
  question about a project can still reach the vault.
* Anywhere else: Hugin is primary, and cwd rides along as a weak hint. It is
  named in the prompt as a place to look for files the question refers to, not
  as the subject.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import CouncilConfig


@dataclass
class WorkContext:
    cwd: Path
    primary: Path
    extra: list[Path]
    repo: Path | None
    hint_only: bool

    @property
    def dirs(self) -> list[Path]:
        return [self.primary, *self.extra]

    def describe(self) -> str:
        """The paragraph the prompts paste in, so every session is told the same
        thing about where it is and why."""
        lines = [f"Working directory: `{self.cwd}`"]
        if self.repo is not None:
            lines.append(
                f"That is inside the project repo `{self.repo}`, which is the "
                "subject unless the question says otherwise."
            )
        else:
            lines.append(
                "That is not a project repo, so treat it only as a weak hint: "
                "somewhere to look for files the question refers to, not as the "
                "subject."
            )
        if self.extra:
            listed = ", ".join(f"`{d}`" for d in self.extra)
            lines.append(f"Also readable: {listed}")
        return "\n".join(lines)


def _resolve_repo(cwd: Path, projects_root: Path) -> Path | None:
    try:
        rel = cwd.resolve().relative_to(projects_root.resolve())
    except (ValueError, OSError):
        return None
    if not rel.parts:
        # Standing in ~/projs itself is not standing in a project.
        return None
    return projects_root.resolve() / rel.parts[0]


def resolve(cfg: CouncilConfig, cwd: Path | None = None) -> WorkContext:
    cwd = Path(cwd or Path.cwd())
    repo = _resolve_repo(cwd, cfg.projects_root)
    hugin_dirs = [d for d in cfg.hugin_dirs if d.exists()]

    if repo is not None:
        extra = [d for d in hugin_dirs if d != repo]
        return WorkContext(cwd=cwd, primary=repo, extra=extra, repo=repo, hint_only=False)

    primary = hugin_dirs[0] if hugin_dirs else cwd
    extra = [d for d in hugin_dirs[1:] if d != primary]
    if cwd not in (primary, *extra):
        extra.append(cwd)
    return WorkContext(cwd=cwd, primary=primary, extra=extra, repo=None, hint_only=True)
