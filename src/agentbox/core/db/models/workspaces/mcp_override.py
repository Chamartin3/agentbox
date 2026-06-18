"""Workspace MCP override models — MCP server and tool-level controls.

Maps to the ``workspace_mcp_overrides``, ``workspace_mcp_tool_overrides``,
and ``workspace_mcp_policies`` tables.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity


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
    )


class WorkspaceMcpPolicy(Entity, table=True):
    """Default MCP access policy for a workspace."""

    __tablename__ = tablename("workspace_mcp_policies")

    workspace_id: str = Field(primary_key=True)
    default_policy: str = Field(nullable=False, default="allow_all_unless_disabled")
