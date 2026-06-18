"""HostEnvProfile model — host environment capability profiles.

Maps to the ``host_env_profiles`` table. Each profile defines a set of
grants (permissions) for interacting with the host environment.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field, UniqueConstraint

from agentbox.core.db.base.model import Entity


class HostEnvProfile(Entity, table=True):
    """A named host environment profile with capability grants."""

    __tablename__ = tablename("host_env_profiles")

    id: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    grants: str = Field(nullable=False, sa_type=JSON)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        UniqueConstraint("name", name="uq_host_env_profile_name"),
    )
