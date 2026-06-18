"""Resource binding models — agent-prompt and workspace-file bindings.

Maps to the ``agent_prompt_resource_bindings`` and
``workspace_file_resource_bindings`` tables.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity


class AgentPromptResourceBinding(Entity, table=True):
    """Links a resource to a slot or marker in an agent's prompt composition."""

    __tablename__ = tablename("agent_prompt_resource_bindings")

    id: str = Field(primary_key=True)
    agent_id: str = Field(nullable=False)
    resource_id: str = Field(foreign_key="resources.id", nullable=False)
    marker: Optional[str] = Field(default=None)
    mode: Optional[str] = Field(default=None)
    slot: Optional[str] = Field(default=None)
    attach_as_reference: int = Field(nullable=False, default=0)
    pinned_version_id: Optional[str] = Field(foreign_key="resource_versions.id", default=None)
    display_order: int = Field(nullable=False, default=0)
    required: int = Field(nullable=False, default=1)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        UniqueConstraint("agent_id", "marker", "resource_id", name="uq_agent_prompt_bindings_triple"),
        Index("ix_agent_prompt_bindings_agent", "agent_id"),
    )


class WorkspaceFileResourceBinding(Entity, table=True):
    """Links a resource to a target file path in a workspace."""

    __tablename__ = tablename("workspace_file_resource_bindings")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    resource_id: str = Field(foreign_key="resources.id", nullable=False)
    target_path: Optional[str] = Field(default=None)
    pinned_version_id: Optional[str] = Field(foreign_key="resource_versions.id", default=None)
    materialize_mode: str = Field(nullable=False, default="copy")
    on_conflict: str = Field(nullable=False, default="error")
    display_order: int = Field(nullable=False, default=0)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        UniqueConstraint("workspace_id", "resource_id", "target_path", name="uq_workspace_file_bindings_triple"),
        Index("ix_workspace_file_bindings_workspace", "workspace_id"),
    )
