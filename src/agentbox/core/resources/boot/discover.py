"""Boot-time skill root discovery helpers."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SKILLS_SOURCES: list[str] = [
    "apps/cvman/mcp/skills",
    "agentbox/skills",
    "skills",
]

_SKILL_ROOT_SKIP_PARTS = frozenset({".venv", "node_modules", ".git"})
_SKILL_ROOT_SKIP_SUFFIXES = ("workdir/worktrees",)


def _is_skipped_skill_root(p: Path) -> bool:
    parts = p.parts
    if any(part in _SKILL_ROOT_SKIP_PARTS for part in parts):
        return True
    s = str(p).replace(os.sep, "/")
    return any(suffix in s for suffix in _SKILL_ROOT_SKIP_SUFFIXES)


def resolve_skill_roots(root: Path) -> list[Path]:
    candidates: list[Path] = [root / rel for rel in DEFAULT_SKILLS_SOURCES]
    extra = os.environ.get("AGENTBOX_EXTRA_SKILL_ROOTS", "")
    for token in extra.split(":"):
        token = token.strip()
        if not token:
            continue
        p = Path(token)
        if not p.is_absolute():
            p = root / p
        candidates.append(p)

    seen: set[Path] = set()
    out: list[Path] = []
    for c in candidates:
        try:
            resolved = c.resolve() if c.exists() else c
        except OSError:
            resolved = c
        if resolved in seen:
            continue
        seen.add(resolved)
        if not c.is_dir():
            continue
        if _is_skipped_skill_root(c):
            continue
        out.append(c)
    return out
