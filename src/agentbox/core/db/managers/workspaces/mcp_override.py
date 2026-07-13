"""Workspace MCP override managers."""
from __future__ import annotations

import uuid
from typing import cast

from agentbox.core.data.rows import WorkspaceMcpOverrideRow, WorkspaceMcpToolOverrideRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.mcp_override import (
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
)
from agentbox.core.db.schema import (
    workspace_mcp_overrides,
    workspace_mcp_policies,
    workspace_mcp_tool_overrides,
)
from agentbox.core.data._util import now_iso
from agentbox.core.data.constants import McpPolicy


class WorkspaceMcpPolicyManager(Manager[WorkspaceMcpPolicy]):
    """Manager for the ``workspace_mcp_policies`` table."""

    model = WorkspaceMcpPolicy

    # ── pure-DB primitives (ported from McpOverridesMixin) ──────────────

    def get_policy(self, workspace_id: str) -> McpPolicy:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_mcp_policies.select().where(
                    workspace_mcp_policies.c.workspace_id == workspace_id
                )
            ).first()
            if not row:
                return McpPolicy.ALLOW_ALL_UNLESS_DISABLED
            return McpPolicy(row.default_policy)

    def set_policy(self, workspace_id: str, policy: McpPolicy) -> McpPolicy:
        with self._engine.begin() as conn:
            existing = conn.execute(
                workspace_mcp_policies.select().where(
                    workspace_mcp_policies.c.workspace_id == workspace_id
                )
            ).first()
            if existing:
                conn.execute(
                    workspace_mcp_policies.update()
                    .where(workspace_mcp_policies.c.workspace_id == workspace_id)
                    .values(default_policy=policy)
                )
            else:
                conn.execute(
                    workspace_mcp_policies.insert().values(
                        workspace_id=workspace_id, default_policy=policy
                    )
                )
        return policy


class WorkspaceMcpOverrideManager(Manager[WorkspaceMcpOverride]):
    """Manager for the ``workspace_mcp_overrides`` table."""

    model = WorkspaceMcpOverride

    # ── pure-DB primitives (ported from McpOverridesMixin) ──────────────

    def list_for_workspace(self, workspace_id: str) -> list[WorkspaceMcpOverrideRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_mcp_overrides.select().where(
                    workspace_mcp_overrides.c.workspace_id == workspace_id
                )
            )
            return [cast(WorkspaceMcpOverrideRow, dict(r._mapping)) for r in rows]

    def set_override(
        self,
        workspace_id: str,
        server_name: str,
        *,
        enabled: bool,
        config_overrides: dict | None = None,
        changelog: str,
        actor: str | None = None,
    ) -> WorkspaceMcpOverrideRow:
        now = now_iso()
        with self._engine.begin() as conn:
            existing = conn.execute(
                workspace_mcp_overrides.select().where(
                    (workspace_mcp_overrides.c.workspace_id == workspace_id)
                    & (workspace_mcp_overrides.c.server_name == server_name)
                )
            ).first()
            if existing:
                conn.execute(
                    workspace_mcp_overrides.update()
                    .where(workspace_mcp_overrides.c.id == existing.id)
                    .values(
                        enabled=1 if enabled else 0,
                        config_overrides=config_overrides,
                        changelog=changelog,
                        created_at=now,
                        created_by=actor,
                    )
                )
                row_id = existing.id
            else:
                row_id = uuid.uuid4().hex
                conn.execute(
                    workspace_mcp_overrides.insert().values(
                        id=row_id,
                        workspace_id=workspace_id,
                        server_name=server_name,
                        enabled=1 if enabled else 0,
                        config_overrides=config_overrides,
                        changelog=changelog,
                        created_at=now,
                        created_by=actor,
                    )
                )
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_mcp_overrides.select().where(
                    workspace_mcp_overrides.c.id == row_id
                )
            ).first()
        assert row is not None
        return cast(WorkspaceMcpOverrideRow, dict(row._mapping))


class WorkspaceMcpToolOverrideManager(Manager[WorkspaceMcpToolOverride]):
    """Manager for the ``workspace_mcp_tool_overrides`` table."""

    model = WorkspaceMcpToolOverride

    # ── pure-DB primitives (ported from McpOverridesMixin) ──────────────

    def list_for_workspace(self, workspace_id: str) -> list[WorkspaceMcpToolOverrideRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_mcp_tool_overrides.select().where(
                    workspace_mcp_tool_overrides.c.workspace_id == workspace_id
                )
            )
            return [cast(WorkspaceMcpToolOverrideRow, dict(r._mapping)) for r in rows]

    def set_override(
        self,
        workspace_id: str,
        server_name: str,
        tool_name: str,
        *,
        enabled: bool,
        actor: str | None = None,
    ) -> WorkspaceMcpToolOverrideRow:
        now = now_iso()
        with self._engine.begin() as conn:
            existing = conn.execute(
                workspace_mcp_tool_overrides.select().where(
                    (workspace_mcp_tool_overrides.c.workspace_id == workspace_id)
                    & (workspace_mcp_tool_overrides.c.server_name == server_name)
                    & (workspace_mcp_tool_overrides.c.tool_name == tool_name)
                )
            ).first()
            if existing:
                conn.execute(
                    workspace_mcp_tool_overrides.update()
                    .where(workspace_mcp_tool_overrides.c.id == existing.id)
                    .values(
                        enabled=1 if enabled else 0, created_at=now, created_by=actor
                    )
                )
                row_id = existing.id
            else:
                row_id = uuid.uuid4().hex
                conn.execute(
                    workspace_mcp_tool_overrides.insert().values(
                        id=row_id,
                        workspace_id=workspace_id,
                        server_name=server_name,
                        tool_name=tool_name,
                        enabled=1 if enabled else 0,
                        created_at=now,
                        created_by=actor,
                    )
                )
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_mcp_tool_overrides.select().where(
                    workspace_mcp_tool_overrides.c.id == row_id
                )
            ).first()
        assert row is not None
        return cast(WorkspaceMcpToolOverrideRow, dict(row._mapping))
