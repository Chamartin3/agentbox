"""Workspace model — workspace registry.

Maps to the ``workspaces`` table. The canonical registry of workspaces
known to agentbox.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class Workspace(Entity, table=True):
    """A named workspace — the unit of organisational grouping in agentbox."""

    __tablename__ = tablename("workspaces")

    name: str = Field(primary_key=True)
    description: Optional[str] = Field(default=None)
    path: Optional[str] = Field(default=None)
    source: str = Field(nullable=False, default="db")
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)
    updated_at: str = Field(nullable=False)
