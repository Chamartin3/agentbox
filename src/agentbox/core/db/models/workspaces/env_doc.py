"""Workspace env-doc models — environment documentation for workspaces.

Maps to the ``workspace_env_docs`` and ``workspace_env_doc_versions`` tables.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity


class WorkspaceEnvDoc(Entity, table=True):
    """Points to the active env-doc version for a workspace."""

    __tablename__ = tablename("workspace_env_docs")

    workspace_id: str = Field(primary_key=True)
    active_version_id: Optional[str] = Field(
        foreign_key="workspace_env_doc_versions.id", ondelete="SET NULL", default=None,
    )


class WorkspaceEnvDocVersion(Entity, table=True):
    """A versioned environment documentation snapshot for a workspace."""

    __tablename__ = tablename("workspace_env_doc_versions")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    version_number: int = Field(nullable=False)
    content_json: dict = Field(nullable=False, sa_type=JSON)
    is_draft: int = Field(nullable=False, default=0)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        UniqueConstraint("workspace_id", "version_number", name="uq_workspace_env_doc_version"),
        Index("ix_workspace_env_doc_versions_workspace_id", "workspace_id"),
    )
