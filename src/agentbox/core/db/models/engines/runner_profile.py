"""RunnerProfile model — runner backend configuration profiles.

Maps to the ``runner_profiles`` table. Each row defines a named backend
configuration (backend, model, credentials, params, etc.).
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class RunnerProfile(Entity, table=True):
    """A named runner profile: backend + model + parameter configuration."""

    __tablename__ = tablename("runner_profiles")

    id: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    backend: str = Field(nullable=False)
    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    api_key_env: Optional[str] = Field(default=None)
    output_mode: str = Field(nullable=False, default="auto")
    params_json: str = Field(nullable=False, default="{}")
    headers_json: str = Field(nullable=False, default="{}")
    extra_args_json: str = Field(nullable=False, default="[]")
    is_enabled: int = Field(nullable=False, default=1)
    is_system_default: int = Field(nullable=False, default=0)
    api_token_id: Optional[str] = Field(foreign_key="api_tokens.id", default=None)
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        Index("idx_runner_profiles_backend_provider", "backend", "provider"),
        Index("idx_runner_profiles_enabled", "is_enabled"),
    )
