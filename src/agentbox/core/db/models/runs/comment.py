"""RunComment model — user comments attached to runs.

Maps to the ``run_comments`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class RunComment(Entity, table=True):
    """A user comment attached to a specific run."""

    __tablename__ = tablename("run_comments")

    id: int = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", nullable=False)
    author: str = Field(nullable=False)
    body: str = Field(nullable=False)
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        Index("idx_run_comments_run", "run_id"),
    )
