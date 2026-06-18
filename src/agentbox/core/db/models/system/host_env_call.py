"""HostEnvCallLog model — audit log of host environment capability invocations.

Maps to the ``host_env_call_log`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class HostEnvCallLog(Entity, table=True):
    """An audit record of a host environment capability call."""

    __tablename__ = tablename("host_env_call_log")

    id: str = Field(primary_key=True)
    run_id: str = Field(nullable=False)
    workspace_id: str = Field(nullable=False)
    capability: str = Field(nullable=False)
    params: Optional[dict] = Field(default=None, sa_type=JSON)
    status: str = Field(nullable=False)
    error: Optional[str] = Field(default=None)
    surface: str = Field(nullable=False, default="host_env")
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        Index("ix_host_env_call_log_run", "run_id"),
        Index("ix_host_env_call_log_workspace", "workspace_id"),
    )
