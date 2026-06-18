"""Run model — core execution record.

Maps to the ``runs`` table. This is the central entity in the agentbox
execution model; every run produces one row.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class Run(Entity, table=True):
    """A single agent execution run.

    ``id`` is a UUID string assigned by the executor. ``status`` follows
    the ``RunStatus`` enum (ok / error / timeout / failed / incomplete /
    running).  Most columns are nullable because they are populated at
    different stages of the run lifecycle.
    """

    __tablename__ = tablename("runs")

    id: str = Field(primary_key=True)
    agent_id: str = Field(nullable=False)
    session_id: Optional[str] = Field(foreign_key="sessions.id", default=None)
    status: str = Field(nullable=False)
    input: str = Field(nullable=False)
    output: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    workdir: Optional[str] = Field(default=None)
    transcript_path: Optional[str] = Field(default=None)
    created_at: str = Field(nullable=False)
    finished_at: Optional[str] = Field(default=None)
    config_digest: Optional[str] = Field(default=None)
    agent_version_id: Optional[int] = Field(foreign_key="agent_versions.id", default=None)
    composition_snapshot: Optional[str] = Field(default=None)
    rendered_prompt: Optional[str] = Field(default=None)
    variables: Optional[str] = Field(default=None)
    validation_status: Optional[str] = Field(default=None)
    validation_errors: Optional[str] = Field(default=None)
    schema_validated_via: Optional[str] = Field(default=None)
    post_status: Optional[str] = Field(default=None)
    post_errors: Optional[str] = Field(default=None)
    conversation_format: Optional[str] = Field(default=None)
    conversation_uri: Optional[str] = Field(default=None)
    runner_profile_id: Optional[str] = Field(foreign_key="runner_profiles.id", default=None)
    resource_snapshot: Optional[str] = Field(default=None)
    mcp_snapshot: Optional[str] = Field(default=None)
    runner_snapshot: Optional[str] = Field(default=None)
    prompt_version_id: Optional[int] = Field(foreign_key="prompt_versions.id", default=None)

    __table_args__ = tableargs(  
        Index("runs_by_agent", "agent_id", "created_at"),
        Index("runs_by_status", "status", "created_at"),
        Index("idx_runs_runner_profile_id", "runner_profile_id"),
    )
