"""``Workspaces`` — the single public entry point of the workspace domain.

Outsiders never touch the composer, renderer, or generation internals; they
call this facade. It owns the compose → render pipeline:

    build(ws)                -> render the persistent workspace workdir
    build(ws, into=run_dir)  -> render a fresh per-run dir (identical output)
    inspect(ws)              -> blueprint summary + last-build provenance
    permissions(agent)       -> the workspace permission overlay for a run
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping

from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.data.workenv import EffectivePermissionsOverlay
from agentbox.core.db import WorkspaceReadManager
from agentbox.core.workspaces._types import WorkspaceSyncMeta
from agentbox.core.workspaces.compose import WorkspaceComposer
from agentbox.core.workspaces.render import (
    BuildResult,
    WorkspaceRenderer,
    _read_previous_meta,
)

_EPHEMERAL = "<ephemeral>"


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
        self._renderer = WorkspaceRenderer(settings)

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
