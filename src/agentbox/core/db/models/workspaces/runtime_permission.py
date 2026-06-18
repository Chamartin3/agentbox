"""WorkspaceRuntimePermission model — runtime permission constraints per workspace.

Maps to the ``workspace_runtime_permissions`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class WorkspaceRuntimePermission(Entity, table=True):
    """Runtime permission constraints applied to runs in a workspace."""

    __tablename__ = tablename("workspace_runtime_permissions")

    workspace_id: str = Field(primary_key=True)
    allowed_builtin_tools: Optional[list[str]] = Field(default=None, sa_type=JSON)
    files: Optional[list[dict]] = Field(default=None, sa_type=JSON)
    max_tokens: Optional[int] = Field(default=None)
    allow_file_write: Optional[int] = Field(default=None)
    allow_network: Optional[int] = Field(default=None)
    updated_at: str = Field(nullable=False)
    updated_by: Optional[str] = Field(default=None)
