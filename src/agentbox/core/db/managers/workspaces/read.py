"""WorkspaceReadManager — purpose-specific READ manager for workspace composition.

Provides a single injected manager for ``compose.py``, bundling the read
queries from 8 existing per-table managers.  Each method copies the exact
SQL the source manager uses — this is a pure-composition convenience, not
a delegating proxy.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

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
from agentbox.core.db.schema import (
    active_agent_versions,
    active_resource_versions,
    agent_versions,
    host_env_profiles,
    resource_blobs,
    resource_versions,
    resources,
    workspace_env_doc_versions,
    workspace_env_docs,
    workspace_file_resource_bindings,
    workspace_mcp_overrides,
    workspace_mcp_policies,
    workspace_mcp_tool_overrides,
    workspace_runtime_permissions,
    workspace_subagents,
    workspaces,
)


class WorkspaceReadManager:
    """Read-only queries aggregated from per-workspace-table managers.

    Every method opens its own connection and returns raw row dicts
    (same shape as the individual managers).  No writes, no business logic.
    """

    def __init__(self, engine: Any) -> None:
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
                    prompt_content=m["prompt_content"],
                    source=m["source"],
                    resolved_tool_grants=m["resolved_tool_grants"],
                )
        # Convert row to AgentDef; return None if it fails validation
        try:
            return AgentDef.from_db_row(row)
        except Exception:
            return None
