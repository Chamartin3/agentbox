"""ApiToken model — API credential tokens for external services.

Maps to the ``api_tokens`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from sqlmodel import Field, UniqueConstraint

from agentbox.core.db.base.model import Entity


class ApiToken(Entity, table=True):
    """An encrypted API token credential for a specific environment."""

    __tablename__ = tablename("api_tokens")

    id: str = Field(primary_key=True)
    environment: str = Field(nullable=False)
    name: str = Field(nullable=False)
    secret_encrypted: str = Field(nullable=False)
    last_four: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        UniqueConstraint("environment", "name", name="uq_api_tokens_env_name"),
    )
