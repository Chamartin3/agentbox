"""Usage model — token and cost tracking for a run.

Maps to the ``usage`` table. Each run has zero or one usage record.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class Usage(Entity, table=True):
    """Token usage and cost tracking for a single run."""

    __tablename__ = tablename("usage")

    run_id: str = Field(primary_key=True, foreign_key="runs.id")
    model: Optional[str] = Field(default=None)
    input_tokens: Optional[int] = Field(default=0)
    output_tokens: Optional[int] = Field(default=0)
    cache_read_tokens: Optional[int] = Field(default=0)
    cache_write_tokens: Optional[int] = Field(default=0)
    cost_usd: Optional[float] = Field(default=None)
