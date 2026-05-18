"""Workspace operations — resolve, create, list, scaffold, generated configs."""

from __future__ import annotations

import json
import shutil
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.config import Settings
from agentbox.core.resource.skills import discover_skills

if TYPE_CHECKING:
    from agentbox.core.data.manifest import AgentDef


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
    store: object | None = None,
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
            get_ws = getattr(store, "get_workspace", None)
            if callable(get_ws):
                row = get_ws(agent.workspace)
                if row and row.get("path"):
                    return settings.project_root / row["path"], False
        return settings.project_root / agent.workspace, False

    return settings.workspaces_root / agent.id, False


def info(
    agent: AgentDef, settings: Settings, store: object | None = None
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
    agent: AgentDef, settings: Settings, store: object | None = None, scaffold: bool = True
) -> Path:
    """Create the workspace if missing. Optionally scaffold a starter CLAUDE.md."""
    path, _ = resolve_path(agent, settings, store)
    path.mkdir(parents=True, exist_ok=True)
    if scaffold and not (path / "CLAUDE.md").exists():
        (path / "CLAUDE.md").write_text(
            _STARTER_CLAUDE_MD.format(agent_id=agent.id), encoding="utf-8"
        )
    return path


def reset(agent: AgentDef, settings: Settings, store: object | None = None) -> Path:
    """Delete and recreate the workspace (drops everything inside)."""
    path, _ = resolve_path(agent, settings, store)
    if path.exists():
        shutil.rmtree(path)
    return ensure(agent, settings, store, scaffold=True)


def list_all(store: object, settings: Settings) -> list[WorkspaceInfo]:
    """List a WorkspaceInfo for every agent known to the DB."""
    from agentbox.core.service.agents import list_all_agents

    return [info(a, settings, store) for a in list_all_agents(store=store)]


# ---------------------------------------------------------------------------
# Deprecated generated config paths — kept for legacy runner compatibility.
# Generated configs are now written to per-run tmpfs dirs by the executor.
# ---------------------------------------------------------------------------


def _generated_dir(workspace_path: Path) -> Path:
    return workspace_path / ".agentbox" / "generated"


def claude_agents_path(workspace_path: Path) -> Path:
    return _generated_dir(workspace_path) / "claude_agents.json"


def claude_settings_path(workspace_path: Path) -> Path:
    return _generated_dir(workspace_path) / "claude_settings.json"


def opencode_config_path(workspace_path: Path) -> Path:
    return _generated_dir(workspace_path) / "opencode.json"


# ---------------------------------------------------------------------------
# Workspace runtime config (permissions/capabilities.json)
# ---------------------------------------------------------------------------


def capabilities_path(workspace_path: Path) -> Path:
    """Return path to the workspace's runtime capabilities config."""
    return workspace_path / "permissions" / "capabilities.json"


def load_capabilities(workspace_path: Path) -> dict:
    """Deprecated: read workspace capabilities.json, returning {} if missing/unparseable.

    This is a compatibility shim. Permissions are now inlined in the manifest
    via WorkspaceDef.allowed_tools, allowed_builtin_tools, etc.

    This function is kept for backwards compatibility and will be removed
    in a future release.

    Schema (all optional):
      - allowed_tools: list[str]
      - mcp_config_path: str | None  (project-relative)
      - max_tokens: int
      - allow_file_write: bool
      - allow_network: bool
    """
    path = capabilities_path(workspace_path)
    if path.is_file():
        warnings.warn(
            f"Found deprecated capabilities.json at {path}. "
            "Permissions are now inlined in agentbox.toml. "
            "Run `agentbox migrate workspace-permissions` to migrate. "
            "See docs/plans/05-workspace-inlining.md",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}
