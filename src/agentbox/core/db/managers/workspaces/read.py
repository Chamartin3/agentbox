"""WorkspaceReadManager — purpose-specific READ manager for workspace composition.

Provides a single injected manager for ``compose.py``, bundling the read
queries from 8 existing per-table managers.  Each method copies the exact
SQL the source manager uses — this is a pure-composition convenience, not
a delegating proxy.
"""

from __future__ import annotations

from typing import Any, cast

from agentbox.core.data.constants import McpPolicy
from agentbox.core.data.rows import (
    EnvDocRow,
    HostEnvProfileRow,
    WorkspaceHostEnvGrantRow,
    WorkspaceMcpOverrideRow,
    WorkspaceMcpToolOverrideRow,
    WorkspaceRow,
    WorkspaceRuntimePermissionRow,
    WorkspaceSubagentRow,
)
from agentbox.core.db.schema import (
    host_env_profiles,
    workspace_env_doc_versions,
    workspace_env_docs,
    workspace_host_env_grants,
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

    def get_workspace(self, workspace_id: str) -> WorkspaceRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspaces.select().where(workspaces.c.id == workspace_id)
            ).first()
            return cast(WorkspaceRow, dict(row._mapping)) if row else None

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

    def get_host_env_grant(self, workspace_id: str) -> WorkspaceHostEnvGrantRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_host_env_grants.select().where(
                    workspace_host_env_grants.c.workspace_id == workspace_id
                )
            ).first()
            return cast(WorkspaceHostEnvGrantRow, dict(row._mapping)) if row else None

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
