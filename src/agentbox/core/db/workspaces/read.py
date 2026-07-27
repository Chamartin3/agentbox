"""WorkspaceReadManager — purpose-specific READ manager for workspace composition.

Provides a single injected manager for ``compose.py``, bundling the read
queries from 8 existing per-table managers.  Each method copies the exact
SQL the source manager uses — this is a pure-composition convenience, not
a delegating proxy.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from sqlalchemy import select

from agentbox.core.data import AgentDef
from agentbox.core.data.constants import McpPolicy
from agentbox.core.data.rows import (
    AgentVersionRow,
    EnvDocRow,
    HostEnvProfileRow,
    RepoResourceRow,
    ResourceBlobRow,
    ResourceVersionRow,
    WorkspaceFileBindingRow,
    WorkspaceMcpOverrideRow,
    WorkspaceMcpToolOverrideRow,
    WorkspaceRow,
    WorkspaceRuntimePermissionRow,
    WorkspaceSubagentRow,
)
from agentbox.core.db.agents.agent import ActiveAgentVersion, AgentRunnerProfile
from agentbox.core.db.agents.version import AgentVersion
from agentbox.core.db.engines.runner_profile import RunnerProfile
from agentbox.core.db.resources.binding import WorkspaceFileResourceBinding
from agentbox.core.db.resources.resource import (
    ActiveResourceVersion,
    Resource,
    ResourceBlob,
    ResourceVersion,
)
from agentbox.core.db.system.host_env_profile import HostEnvProfile
from agentbox.core.db.workspaces.env_doc import (
    WorkspaceEnvDoc,
    WorkspaceEnvDocVersion,
)
from agentbox.core.db.workspaces.mcp_override import (
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
)
from agentbox.core.db.workspaces.runtime_permission import WorkspaceRuntimePermission
from agentbox.core.db.workspaces.subagent import WorkspaceSubagent
from agentbox.core.db.workspaces.workspace import Workspace

active_agent_versions = ActiveAgentVersion.__table__
agent_versions = AgentVersion.__table__
active_resource_versions = ActiveResourceVersion.__table__
resource_blobs = ResourceBlob.__table__
resource_versions = ResourceVersion.__table__
resources = Resource.__table__
host_env_profiles = HostEnvProfile.__table__
workspace_file_resource_bindings = WorkspaceFileResourceBinding.__table__
workspace_env_doc_versions = WorkspaceEnvDocVersion.__table__
workspace_env_docs = WorkspaceEnvDoc.__table__
workspace_mcp_overrides = WorkspaceMcpOverride.__table__
workspace_mcp_policies = WorkspaceMcpPolicy.__table__
workspace_mcp_tool_overrides = WorkspaceMcpToolOverride.__table__
workspace_runtime_permissions = WorkspaceRuntimePermission.__table__
workspace_subagents = WorkspaceSubagent.__table__
workspaces = Workspace.__table__
runner_profiles = RunnerProfile.__table__
agent_runner_profiles = AgentRunnerProfile.__table__


class WorkspaceReadManager:
    """Read-only queries aggregated from per-workspace-table managers.

    Every method opens its own connection and returns raw row dicts
    (same shape as the individual managers).  No writes, no business logic.
    """

    def __init__(self, engine) -> None:
        self._engine = engine

    # ── Workspace ─────────────────────────────────────────────────────────────

    def get_workspace_by_name(self, name: str) -> WorkspaceRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspaces.select().where(workspaces.c.name == name)
            ).first()
            return cast(WorkspaceRow, dict(row._mapping)) if row else None

    def list_workspaces(self) -> list[WorkspaceRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspaces.select().order_by(workspaces.c.name)
            )
            return [cast(WorkspaceRow, dict(r._mapping)) for r in rows]

    # ── Env-doc ───────────────────────────────────────────────────────────────

    def get_active_env_doc(self, workspace_id: str) -> EnvDocRow | None:
        with self._engine.connect() as conn:
            ptr = conn.execute(
                workspace_env_docs.select().where(
                    workspace_env_docs.c.workspace_id == workspace_id
                )
            ).first()
            if not ptr or not ptr.active_version_id:
                return None
            ver = conn.execute(
                workspace_env_doc_versions.select().where(
                    workspace_env_doc_versions.c.id == ptr.active_version_id
                )
            ).first()
            return cast(EnvDocRow, dict(ver._mapping)) if ver else None

    def list_env_doc_versions(self, workspace_id: str) -> list[EnvDocRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_env_doc_versions.select()
                .where(workspace_env_doc_versions.c.workspace_id == workspace_id)
                .order_by(workspace_env_doc_versions.c.version_number.desc())
            )
            return [cast(EnvDocRow, dict(r._mapping)) for r in rows]

    # ── Subagents ─────────────────────────────────────────────────────────────

    def list_subagents(self, workspace_id: str) -> list[WorkspaceSubagentRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_subagents.select()
                .where(workspace_subagents.c.workspace_id == workspace_id)
                .order_by(workspace_subagents.c.display_order)
            )
            return [cast(WorkspaceSubagentRow, dict(r._mapping)) for r in rows]

    def list_workspace_engines(self, workspace_id: str) -> set[str]:
        """Engines the workspace's related agents resolve to — the build default.

        Related agents = the workspace's own agent (when ``workspace_id`` names
        one) plus its subagents. Each agent's engine is its bound runner
        profile's ``backend``; an agent with no bound profile uses the
        system-default profile. Empty when the workspace has no agents — the
        caller then falls back to rendering every installed engine.
        """
        agent_ids = [r["agent_id"] for r in self.list_subagents(workspace_id)]
        with self._engine.connect() as conn:
            is_own_agent = conn.execute(
                select(agent_versions.c.id)
                .where(agent_versions.c.agent_id == workspace_id)
                .limit(1)
            ).first() is not None
            if is_own_agent:
                agent_ids.append(workspace_id)
            if not agent_ids:
                return set()

            rows = conn.execute(
                select(agent_runner_profiles.c.agent_id, runner_profiles.c.backend)
                .select_from(
                    agent_runner_profiles.join(
                        runner_profiles,
                        agent_runner_profiles.c.runner_profile_id == runner_profiles.c.id,
                    )
                )
                .where(agent_runner_profiles.c.agent_id.in_(agent_ids))
            ).all()
            engines = {r.backend for r in rows}

            bound = {r.agent_id for r in rows}
            if any(a not in bound for a in agent_ids):
                # Unbound agents dispatch to the system-default profile.
                default = conn.execute(
                    select(runner_profiles.c.backend)
                    .where(runner_profiles.c.is_system_default == 1)
                    .limit(1)
                ).scalar()
                if default:
                    engines.add(default)
        return engines

    # ── MCP overrides & policy ────────────────────────────────────────────────

    def list_mcp_overrides(self, workspace_id: str) -> list[WorkspaceMcpOverrideRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_mcp_overrides.select().where(
                    workspace_mcp_overrides.c.workspace_id == workspace_id
                )
            )
            return [cast(WorkspaceMcpOverrideRow, dict(r._mapping)) for r in rows]

    def list_mcp_tool_overrides(self, workspace_id: str) -> list[WorkspaceMcpToolOverrideRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_mcp_tool_overrides.select().where(
                    workspace_mcp_tool_overrides.c.workspace_id == workspace_id
                )
            )
            return [cast(WorkspaceMcpToolOverrideRow, dict(r._mapping)) for r in rows]

    def get_mcp_policy(self, workspace_id: str) -> McpPolicy:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_mcp_policies.select().where(
                    workspace_mcp_policies.c.workspace_id == workspace_id
                )
            ).first()
            if not row:
                return McpPolicy.ALLOW_ALL_UNLESS_DISABLED
            return McpPolicy(row.default_policy)

    # ── Runtime permissions ───────────────────────────────────────────────────

    def get_runtime_permissions(self, workspace_id: str) -> WorkspaceRuntimePermissionRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_runtime_permissions.select().where(
                    workspace_runtime_permissions.c.workspace_id == workspace_id
                )
            ).first()
            return cast(WorkspaceRuntimePermissionRow, dict(row._mapping)) if row else None

    # ── Host-env grants ───────────────────────────────────────────────────────

    def list_host_env_profiles(self) -> list[HostEnvProfileRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                host_env_profiles.select().order_by(host_env_profiles.c.name)
            )
            return [cast(HostEnvProfileRow, dict(r._mapping)) for r in rows]

    def get_host_env_profile(self, profile_id: str) -> HostEnvProfileRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                host_env_profiles.select().where(host_env_profiles.c.id == profile_id)
            ).first()
            return cast(HostEnvProfileRow, dict(row._mapping)) if row else None

    # ── File bindings ─────────────────────────────────────────────────────────

    def list_file_bindings(self, workspace_id: str) -> list[WorkspaceFileBindingRow]:
        """Return all file bindings for a workspace ordered by display_order."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_file_resource_bindings.select()
                .where(workspace_file_resource_bindings.c.workspace_id == workspace_id)
                .order_by(workspace_file_resource_bindings.c.display_order)
            )
            return [cast(WorkspaceFileBindingRow, dict(r._mapping)) for r in rows]

    # ── Resources ─────────────────────────────────────────────────────────────

    def get_resource(self, resource_id: str) -> RepoResourceRow | None:
        """Fetch a resource row by id. Returns a typed row or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                resources.select().where(resources.c.id == resource_id)
            ).first()
            return cast(RepoResourceRow, dict(row._mapping)) if row else None

    def get_active_resource_version(self, resource_id: str) -> ResourceVersionRow | None:
        """Return the currently active version row as a typed row, or None."""
        with self._engine.connect() as conn:
            # Get the active version_id first
            active_row = conn.execute(
                active_resource_versions.select().where(
                    active_resource_versions.c.resource_id == resource_id
                )
            ).first()
            if not active_row:
                return None
            # Then fetch the version row
            ver_row = conn.execute(
                resource_versions.select().where(
                    resource_versions.c.id == active_row._mapping["version_id"]
                )
            ).first()
            return cast(ResourceVersionRow, dict(ver_row._mapping)) if ver_row else None

    def get_resource_version(self, version_id: str) -> ResourceVersionRow | None:
        """Fetch a version row by id. Returns typed row or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                resource_versions.select().where(resource_versions.c.id == version_id)
            ).first()
            return cast(ResourceVersionRow, dict(row._mapping)) if row else None

    def iter_blobs(self, version_id: str) -> Iterator[ResourceBlobRow]:
        """Yield all blobs for a version ordered by relative_path."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                resource_blobs.select()
                .where(resource_blobs.c.resource_version_id == version_id)
                .order_by(resource_blobs.c.relative_path)
            )
            for r in rows:
                yield cast(ResourceBlobRow, dict(r._mapping))

    # ── Agent versions and definitions ────────────────────────────────────────

    def get_active_agent_version(self, agent_id: str) -> AgentVersionRow | None:
        """Row pointed at by ``active_agent_versions``, or None if unset."""
        with self._engine.connect() as conn:
            pointer = conn.execute(
                active_agent_versions.select().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            ).first()
            if pointer is None:
                return None
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.id == pointer._mapping["version_id"]
                )
            ).first()
            if not row:
                return None
            m = row._mapping
            return AgentVersionRow(
                id=m["id"],
                agent_id=m["agent_id"],
                version=m["version"],
                source_path=m["source_path"],
                source_format=m["source_format"],
                content_snapshot=m["content_snapshot"],
                prompt_snapshot=m["prompt_snapshot"],
                content_hash=m["content_hash"],
                author=m["author"],
                changelog=m["changelog"],
                is_legacy=bool(m["is_legacy"]),
                created_at=m["created_at"],
                config_json=m["config_json"],
                workspace_name=m["workspace_name"],
                prompt_content=m["prompt_content"],
                source=m["source"],
                resolved_tool_grants=m["resolved_tool_grants"],
            )

    def get_agent_def(self, agent_id: str) -> AgentDef | None:
        """Return the ``AgentDef`` for *agent_id*, or ``None``.

        ``None`` when the agent has never been versioned or the stored
        snapshot fails validation.
        """
        # Try to get active version, then fallback to latest
        row = self.get_active_agent_version(agent_id)
        if row is None:
            # Get latest version instead
            with self._engine.connect() as conn:
                latest_row = conn.execute(
                    agent_versions.select()
                    .where(agent_versions.c.agent_id == agent_id)
                    .order_by(agent_versions.c.version.desc())
                    .limit(1)
                ).first()
                if not latest_row:
                    return None
                m = latest_row._mapping
                row = AgentVersionRow(
                    id=m["id"],
                    agent_id=m["agent_id"],
                    version=m["version"],
                    source_path=m["source_path"],
                    source_format=m["source_format"],
                    content_snapshot=m["content_snapshot"],
                    prompt_snapshot=m["prompt_snapshot"],
                    content_hash=m["content_hash"],
                    author=m["author"],
                    changelog=m["changelog"],
                    is_legacy=bool(m["is_legacy"]),
                    created_at=m["created_at"],
                    config_json=m["config_json"],
                    workspace_name=m["workspace_name"],
                    prompt_content=m["prompt_content"],
                    source=m["source"],
                    resolved_tool_grants=m["resolved_tool_grants"],
                )
        # Convert row to AgentDef; return None if it fails validation
        try:
            return AgentDef.from_db_row(row)
        except Exception:
            return None
