"""Runner profile data shapes — pure Pydantic models, no persistence.

These are extracted from the legacy ``core.db.engines.profiles`` module which
also carries ``RunnerProfilesMixin`` (CRUD against SQLAlchemy tables). Only the
pure value types live here.
"""

from __future__ import annotations

from agentbox.core.data.payload_types import ModelParams
from pydantic import BaseModel, Field



class RunnerProfile(BaseModel):
    """A runtime configuration profile for agent execution."""

    id: str
    name: str
    description: str | None = None
    backend: str
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_token_id: str | None = None
    output_mode: str = "auto"
    params: ModelParams = Field(default_factory=ModelParams)
    headers: dict[str, str] = Field(default_factory=dict)
    extra_args: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    is_system_default: bool = False
    created_at: str
    updated_at: str


class RunnerProfileCreate(BaseModel):
    """Mutable fields for creating a new runner profile."""

    id: str | None = None
    name: str
    description: str | None = None
    backend: str
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_token_id: str | None = None
    output_mode: str = "auto"
    params: ModelParams = Field(default_factory=ModelParams)
    headers: dict[str, str] = Field(default_factory=dict)
    extra_args: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    is_system_default: bool = False


class RunnerProfilePatch(BaseModel):
    """Mutable fields for updating a runner profile."""

    name: str | None = None
    description: str | None = None
    backend: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_token_id: str | None = None
    output_mode: str | None = None
    params: ModelParams | None = None
    headers: dict[str, str] | None = None
    extra_args: list[str] | None = None
    is_enabled: bool | None = None
    is_system_default: bool | None = None


class RunnerProfileStats(BaseModel):
    """Statistics for a runner profile."""

    profile_id: str
    runs: int
    succeeded: int
    failed: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None
    avg_duration_ms: float | None = None
    last_run_at: str | None = None
