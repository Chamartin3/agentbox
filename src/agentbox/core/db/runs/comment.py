"""RunComment model + manager — user comments attached to runs.

Maps to the ``run_comments`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import cast

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity
from agentbox.core.data.rows import RunCommentRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.schema import run_comments
from agentbox.core.data._util import now_iso


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


class RunCommentManager(Manager[RunComment]):
    """Manager for the ``run_comments`` table."""

    model = RunComment

    def add(self, run_id: str, author: str, body: str) -> RunCommentRow:
        """Insert a comment on a run and return the new typed row."""
        with self._engine.begin() as conn:
            result = conn.execute(
                run_comments.insert().values(
                    run_id=run_id,
                    author=author,
                    body=body,
                    created_at=now_iso(),
                )
            )
            pk = result.inserted_primary_key
            new_id = pk[0] if pk is not None else None
            row = conn.execute(
                run_comments.select().where(run_comments.c.id == new_id)
            ).first()
        assert row is not None, "just-inserted comment must be retrievable"
        return cast(RunCommentRow, dict(row._mapping))

    def list_for_run(self, run_id: str) -> list[RunCommentRow]:
        """List all comments for a run ordered by created_at."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                run_comments.select()
                .where(run_comments.c.run_id == run_id)
                .order_by(run_comments.c.created_at)
            )
            return [cast(RunCommentRow, dict(r._mapping)) for r in rows]
