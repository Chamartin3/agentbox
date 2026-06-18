"""Workspace CRUD operations — resolve, info, ensure, reset.

Pure operations on workspace paths; no DB writes, no deprecated config paths.
Deprecated shims live in ``manager.py`` for backward compatibility.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.config import Settings
from agentbox.core.resources.skills import discover_skills

if TYPE_CHECKING:
    from agentbox.core.db import AgentDef, SessionStore, WorkspaceLookupStore


@dataclass(frozen=True)
class WorkspaceInfo:
    agent_id: str
    path: Path
    exists: bool
    ephemeral: bool
    """True if the agent is configured to use a tmp dir per run."""

    has_claude_md: bool
    skill_count: int


def resolve_path(
    agent: AgentDef,
    settings: Settings,
    store: WorkspaceLookupStore | None = None,
) -> tuple[Path, bool]:
    """Return (workspace_path, is_ephemeral) for an agent.

    Resolution order:
    1. "<ephemeral>" → tmp dir per run
    2. Named workspace reference → DB workspaces table
    3. Explicit path → project-relative path
    4. Omitted → auto-resolved to ``<workspaces_root>/<agent_id>/``
    """
    if agent.workspace == "<ephemeral>":
        return settings.workspaces_root / agent.id, True

    if agent.workspace:
        if store is not None:
            row = store.get_workspace(agent.workspace)
            row_path = row.get("path") if row else None
            if row_path:
                return settings.project_root / row_path, False
        return settings.project_root / agent.workspace, False

    return settings.workspaces_root / agent.id, False


def info(
    agent: AgentDef, settings: Settings, store: SessionStore | None = None
) -> WorkspaceInfo:
    path, ephemeral = resolve_path(agent, settings, store)
    has_claude_md = (path / "CLAUDE.md").exists() if path.exists() else False
    skill_count = len(discover_skills(path)) if path.exists() else 0
    return WorkspaceInfo(
        agent_id=agent.id,
        path=path,
        exists=path.exists(),
        ephemeral=ephemeral,
        has_claude_md=has_claude_md,
        skill_count=skill_count,
    )


_STARTER_CLAUDE_MD = """\
# {agent_id} workspace

This directory is the working directory the agent sees when it runs.

Add anything the agent should be able to read here:
- Edit this `CLAUDE.md` to set persistent guidance / project context.
- Drop reference files (data, notes, examples) at any path.
- Put reusable instructions under `skills/<skill-name>/SKILL.md`.

Edit freely — changes take effect on the next run.
"""


def ensure(
    agent: AgentDef,
    settings: Settings,
    store: SessionStore | None = None,
    scaffold: bool = True,
) -> Path:
    """Create the workspace if missing. Optionally scaffold a starter CLAUDE.md."""
    path, _ = resolve_path(agent, settings, store)
    path.mkdir(parents=True, exist_ok=True)
    if scaffold and not (path / "CLAUDE.md").exists():
        (path / "CLAUDE.md").write_text(
            _STARTER_CLAUDE_MD.format(agent_id=agent.id), encoding="utf-8"
        )
    return path


def reset(agent: AgentDef, settings: Settings, store: SessionStore | None = None) -> Path:
    """Delete and recreate the workspace (drops everything inside)."""
    path, _ = resolve_path(agent, settings, store)
    if path.exists():
        shutil.rmtree(path)
    return ensure(agent, settings, store, scaffold=True)
