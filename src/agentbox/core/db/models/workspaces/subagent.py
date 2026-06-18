"""WorkspaceSubagent model — subagent mappings within a workspace.

Maps to the ``workspace_subagents`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity


class WorkspaceSubagent(Entity, table=True):
    """A subagent (agent alias registration) within a workspace."""

    __tablename__ = tablename("workspace_subagents")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    agent_id: str = Field(nullable=False)
    alias: str = Field(nullable=False)
    display_order: int = Field(nullable=False, default=0)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        UniqueConstraint("workspace_id", "alias", name="uq_workspace_subagents_alias"),
        Index("ix_workspace_subagents_workspace", "workspace_id"),
    )
