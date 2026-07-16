"""Workspace domain — the ``Workspaces`` facade is the only public surface.

Responsibilities split by submodule (outsiders import only this package root):

- ``compose``  — DB state → immutable ``WorkspaceBlueprint`` (+ ``WorkspaceInspection``). No I/O.
- ``build``    — blueprint → disk (``WorkspaceBuilder``, ``BuildResult``, the write pipeline).
- ``tooling``  — MCP servers: install / list / talk (zero policy).
- ``workdir``  — path resolution (``resolve_path`` for agents, ``resolve_workspace_workdir`` for names).

``Workspaces`` is pure delegation over ``compose`` → ``build``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.data.payload_types import EnvDocRenderEntry, McpStdioServerSpec
from agentbox.core.data.workenv import EffectivePermissionsOverlay
from agentbox.core.db import WorkspaceReadManager
from agentbox.core.workspaces.build import (
    BuildResult as BuildResult,
    WorkspaceBuilder,
    _read_previous_meta,
)
from agentbox.core.workspaces.build.engine import render_context_only
from agentbox.core.workspaces.compose import (
    WorkspaceComposer,
    WorkspaceInspection as WorkspaceInspection,
)
from agentbox.core.workspaces.workdir import (
    WorkspaceInfo as WorkspaceInfo,
    resolve_path as resolve_path,
    resolve_workspace_workdir,
)

_EPHEMERAL = "<ephemeral>"

__all__ = [
    "BuildResult",
    "WorkspaceInfo",
    "WorkspaceInspection",
    "Workspaces",
    "resolve_path",
]


class Workspaces:
    """Facade over compose + build. Constructed once with a read manager."""

    def __init__(self, reads: WorkspaceReadManager, settings: Settings) -> None:
        self._reads = reads
        self._settings = settings
        self._composer = WorkspaceComposer(reads)
        self._builder = WorkspaceBuilder(settings)

    def build(
        self,
        workspace_id: str = "default",
        *,
        into: Path | None = None,
        engines: Collection[str] | None = None,
        system_prompt: str | None = None,
        secrets: Mapping[str, str] | None = None,
        extra_mcp_servers: Mapping[str, McpStdioServerSpec] | None = None,
    ) -> BuildResult:
        """Render a workspace onto disk.

        ``engines`` restricts which engine configs are rendered (``None`` = all).
        A subset is additive: engine files aren't orphan-reconciled, so engines
        already on disk from a prior build survive.

        ``into=None`` renders the persistent workspace workdir (orphan
        reconcile + provenance). ``into=path`` renders a fresh per-run dir
        with identical content but no reconcile/provenance. An empty or
        ``<ephemeral>`` workspace with ``into=None`` never touches disk.
        ``extra_mcp_servers`` are run-scoped intrinsic servers (host_env /
        agent_tools) merged into the run dir's ``.mcp.json``.
        """
        if into is None:
            workdir = resolve_workspace_workdir(self._reads, self._settings, workspace_id)
            if workdir is None:
                return BuildResult(workspace_id=workspace_id, target_dir=Path())
            target_dir = workdir
            persistent = True
        else:
            target_dir = Path(into)
            target_dir.mkdir(parents=True, exist_ok=True)
            persistent = False

        blueprint = self._composer.compose(workspace_id, engines=engines)
        return self._builder.render(
            blueprint,
            target_dir,
            persistent=persistent,
            system_prompt=system_prompt,
            secrets=secrets,
            extra_mcp_servers=extra_mcp_servers,
        )

    def inspect(self, workspace_id: str = "default") -> WorkspaceInspection:
        """Summarize composed state plus the last persistent build's provenance."""
        blueprint = self._composer.compose(workspace_id)
        workdir = resolve_workspace_workdir(self._reads, self._settings, workspace_id)
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
