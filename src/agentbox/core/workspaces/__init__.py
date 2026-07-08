"""Workspace domain — the ``Workspaces`` facade is the only public surface.

Responsibilities are split by submodule:

- ``compose``    — DB state → immutable ``WorkspaceBlueprint`` (no I/O).
- ``render``     — blueprint → disk (``WorkspaceBuilder``, ``BuildResult``).
- ``generation`` — the engine-agnostic write pipeline render delegates to.
- ``factory``    — wires the engine recipe registry into that pipeline.
- ``mcp``        — external MCP client + per-workspace server resolution.
- ``catalog``    — tool-surface aggregation.
- ``workdir``    — workspace path resolution + on-disk inspection.

``Workspaces`` (defined here) composes ``compose`` → ``render`` behind
``build`` / ``inspect`` / ``render_env_doc`` / ``permissions``. Outsiders
import only from this package root, never the submodules.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.data.payload_types import EnvDocRenderEntry
from agentbox.core.data.workenv import EffectivePermissionsOverlay
from agentbox.core.db import WorkspaceReadManager
from agentbox.core.resources.skills import discover_skills as discover_skills
from agentbox.core.workspaces._types import WorkspaceSyncMeta
from agentbox.core.workspaces.compose import WorkspaceComposer
from agentbox.core.workspaces.build.bindings import (
    materialize_workspace as materialize_workspace,
)
from agentbox.core.workspaces.tooling.mcp.registry import McpRegistry as McpRegistry
from agentbox.core.workspaces.build.engine import render_context_only
from agentbox.core.workspaces.build import (
    BuildResult as BuildResult,
    WorkspaceBuilder,
    _read_previous_meta,
)
from agentbox.core.workspaces.workdir import (
    WorkspaceInfo as WorkspaceInfo,
    resolve_path as resolve_path,
)

_EPHEMERAL = "<ephemeral>"

__all__ = [
    "BuildResult",
    "McpRegistry",
    "WorkspaceInfo",
    "WorkspaceInspection",
    "Workspaces",
    "discover_skills",
    "materialize_workspace",
    "resolve_path",
]


@dataclass(frozen=True)
class WorkspaceInspection:
    """A read-only summary of a workspace's composed state + last build."""

    workspace_id: str
    workdir: Path | None
    engines: tuple[str, ...]
    agent_count: int
    binding_count: int
    has_env_doc: bool
    last_build: WorkspaceSyncMeta | None


class Workspaces:
    """Facade over compose + render. Constructed once with a read manager."""

    def __init__(self, reads: WorkspaceReadManager, settings: Settings) -> None:
        self._reads = reads
        self._settings = settings
        self._composer = WorkspaceComposer(reads)
        self._renderer = WorkspaceBuilder(settings)

    def build(
        self,
        workspace_id: str = "default",
        *,
        into: Path | None = None,
        system_prompt: str | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> BuildResult:
        """Render a workspace onto disk.

        ``into=None`` renders the persistent workspace workdir (orphan
        reconcile + provenance). ``into=path`` renders a fresh per-run dir
        with identical content but no reconcile/provenance. An empty or
        ``<ephemeral>`` workspace with ``into=None`` never touches disk.
        """
        if into is None:
            workdir = self._resolve_workdir(workspace_id)
            if workdir is None:
                return BuildResult(workspace_id=workspace_id, target_dir=Path())
            target_dir = workdir
            persistent = True
        else:
            target_dir = Path(into)
            target_dir.mkdir(parents=True, exist_ok=True)
            persistent = False

        blueprint = self._composer.compose(workspace_id)
        return self._renderer.render(
            blueprint,
            target_dir,
            persistent=persistent,
            system_prompt=system_prompt,
            secrets=secrets,
        )

    def inspect(self, workspace_id: str = "default") -> WorkspaceInspection:
        """Summarize composed state plus the last persistent build's provenance."""
        blueprint = self._composer.compose(workspace_id)
        workdir = self._resolve_workdir(workspace_id)
        meta = (
            _read_previous_meta(workdir)
            if workdir is not None and workdir.exists()
            else None
        )
        return WorkspaceInspection(
            workspace_id=workspace_id,
            workdir=workdir,
            engines=tuple(r.engine for r in blueprint.recipes),
            agent_count=len(blueprint.config.agents),
            binding_count=len(blueprint.bindings),
            has_env_doc=blueprint.env_doc_body is not None,
            last_build=meta or None,
        )

    def render_env_doc(self, workspace_id: str, into: Path) -> list[EnvDocRenderEntry]:
        """Render ONLY the env-doc instruction files (CLAUDE.md / AGENTS.md)
        into ``into`` and return the snapshot entries. Unlike ``build`` this
        writes no native config — used for previews and shell-side env-doc
        rendering into an arbitrary directory.
        """
        blueprint = self._composer.compose(workspace_id)
        if blueprint.env_doc_body is None:
            return []
        into = Path(into)
        into.mkdir(parents=True, exist_ok=True)
        version_id = blueprint.env_doc_version_id or ""
        entries: list[EnvDocRenderEntry] = []
        for item in render_context_only(into, blueprint.config, list(blueprint.recipes)):
            entries.append(
                {
                    "role": "env_doc",
                    "file": item.file,
                    "workspace_id": workspace_id,
                    "env_doc_version_id": version_id,
                    "bytes": item.bytes,
                }
            )
        return entries

    def permissions(self, agent: AgentDef) -> EffectivePermissionsOverlay | None:
        """Resolve the workspace permission overlay for an agent's run."""
        if not agent.workspace or agent.workspace == _EPHEMERAL:
            return None
        return self._composer._permissions(agent.workspace)

    # ── internal ──────────────────────────────────────────────────────────

    def _resolve_workdir(self, workspace_id: str) -> Path | None:
        """Resolve a workspace name → on-disk persistent workdir path."""
        if not workspace_id or workspace_id == _EPHEMERAL:
            return None
        record = self._reads.get_workspace_by_name(workspace_id)
        if record is not None:
            rel = record["path"]
            if rel:
                return (self._settings.project_root / rel).resolve()
        candidate = self._settings.workspaces_root / workspace_id
        return candidate if candidate.exists() else None
