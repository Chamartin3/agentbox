"""RunPrompt model — captured prompt fragments for a run.

Maps to the ``run_prompts`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class RunPrompt(Entity, table=True):
    """Captured prompt fragments (provenance metadata) for a run."""

    __tablename__ = tablename("run_prompts")

    run_id: str = Field(primary_key=True, foreign_key="runs.id")
    fragments: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
