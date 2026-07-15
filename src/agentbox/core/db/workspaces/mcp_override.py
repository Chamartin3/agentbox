"""Workspace MCP override models and managers — MCP server and tool-level controls.

Maps to the ``workspace_mcp_overrides``, ``workspace_mcp_tool_overrides``,
and ``workspace_mcp_policies`` tables.
"""
from __future__ import annotations

import uuid
from typing import Optional, cast

from sqlalchemy import JSON
from sqlmodel import CheckConstraint, Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs
from agentbox.core.data._util import now_iso
from agentbox.core.data.constants import McpPolicy
from agentbox.core.data.rows import WorkspaceMcpOverrideRow, WorkspaceMcpToolOverrideRow


class WorkspaceMcpOverride(Entity, table=True):
    """Per-workspace MCP server toggle with optional config override."""

    __tablename__ = tablename("workspace_mcp_overrides")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    server_name: str = Field(nullable=False)
    enabled: int = Field(nullable=False)
    config_overrides: Optional[dict] = Field(default=None, sa_type=JSON)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(
        UniqueConstraint("workspace_id", "server_name", name="uq_workspace_mcp_override"),
        Index("ix_workspace_mcp_overrides_workspace", "workspace_id"),
    )


class WorkspaceMcpToolOverride(Entity, table=True):
    """Per-workspace per-tool enable/disable within an MCP server."""

    __tablename__ = tablename("workspace_mcp_tool_overrides")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    server_name: str = Field(nullable=False)
    tool_name: str = Field(nullable=False)
    enabled: int = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(
        UniqueConstraint("workspace_id", "server_name", "tool_name", name="uq_workspace_mcp_tool_override"),
        Index("ix_workspace_mcp_tool_overrides_workspace", "workspace_id"),
    )


class WorkspaceMcpPolicy(Entity, table=True):
    """Default MCP access policy for a workspace."""

    __tablename__ = tablename("workspace_mcp_policies")

    workspace_id: str = Field(primary_key=True)
    default_policy: str = Field(nullable=False, default="allow_all_unless_disabled", sa_column_kwargs={"server_default": "allow_all_unless_disabled"})

    __table_args__ = tableargs(
        CheckConstraint("default_policy IN ('allow_all_unless_disabled', 'deny_all_unless_enabled')", name="workspace_mcp_policy_check"),
    )


workspace_mcp_overrides = WorkspaceMcpOverride.__table__
workspace_mcp_policies = WorkspaceMcpPolicy.__table__
workspace_mcp_tool_overrides = WorkspaceMcpToolOverride.__table__


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
