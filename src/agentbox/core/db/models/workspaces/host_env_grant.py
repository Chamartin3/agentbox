"""WorkspaceHostEnvGrant model — host environment profile grants per workspace.

Maps to the ``workspace_host_env_grants`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class WorkspaceHostEnvGrant(Entity, table=True):
    """Host environment profile linked to a workspace with optional overrides."""

    __tablename__ = tablename("workspace_host_env_grants")

    workspace_id: str = Field(primary_key=True)
    profile_id: Optional[str] = Field(
        foreign_key="host_env_profiles.id", ondelete="SET NULL", default=None,
    )
    overrides: Optional[dict] = Field(default=None, sa_type=JSON)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)
