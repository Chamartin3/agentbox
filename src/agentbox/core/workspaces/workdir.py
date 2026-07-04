"""Workspace directory resolution.

Locates the workdir an agent runs in (``resolve_path``), inspects it
(``info``), creates the directory (``ensure``), and wipes it (``reset``).
Pure filesystem/path operations — no DB writes, no content generation.

The instruction file an agent reads is engine-specific (Claude → CLAUDE.md,
OpenCode/Codex → AGENTS.md); the names come from each backend's recipe via
``recipe_loader.context_filenames`` — never hardcoded here.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.db import WorkspaceManager
from agentbox.core.engines.backends.recipe_loader import context_filenames
from agentbox.core.resources.skills import discover_skills


@dataclass(frozen=True)
class WorkspaceInfo:
    agent_id: str
    path: Path
    exists: bool
    ephemeral: bool
    """True if the agent is configured to use a tmp dir per run."""

    has_context_doc: bool
    """True if any engine's instruction file (CLAUDE.md / AGENTS.md) exists."""

    skill_count: int


def resolve_path(
    agent: AgentDef,
    settings: Settings,
    store: WorkspaceManager | None = None,
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
            row = store.get_by_name(agent.workspace)
            row_path = row.get("path") if row else None
            if row_path:
                return settings.project_root / row_path, False
        return settings.project_root / agent.workspace, False

    return settings.workspaces_root / agent.id, False


def info(
    agent: AgentDef, settings: Settings, store: WorkspaceManager | None = None
) -> WorkspaceInfo:
    path, ephemeral = resolve_path(agent, settings, store)
    exists = path.exists()
    has_context_doc = exists and any((path / n).exists() for n in context_filenames())
    skill_count = len(discover_skills(path)) if exists else 0
    return WorkspaceInfo(
        agent_id=agent.id,
        path=path,
        exists=exists,
        ephemeral=ephemeral,
        has_context_doc=has_context_doc,
        skill_count=skill_count,
    )


def ensure(
    agent: AgentDef,
    settings: Settings,
    store: WorkspaceManager | None = None,
) -> Path:
    """Create the workspace directory if missing, and return its path.

    Instruction files (CLAUDE.md / AGENTS.md) are NOT written here: they are
    render artifacts produced from the workspace's env-doc by
    ``build_workspace`` on every run, so a starter written here would just be
    overwritten. This only guarantees the directory exists.
    """
    path, _ = resolve_path(agent, settings, store)
    path.mkdir(parents=True, exist_ok=True)
    return path


def reset(agent: AgentDef, settings: Settings, store: WorkspaceManager | None = None) -> Path:
    """Delete and recreate the workspace (drops everything inside)."""
    path, _ = resolve_path(agent, settings, store)
    if path.exists():
        shutil.rmtree(path)
    return ensure(agent, settings, store)
