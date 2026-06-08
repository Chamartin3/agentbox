"""Run comment CRUD mixin."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from agentbox.core.data.schema import run_comments
from agentbox.core.data.utils import now_iso


class RunCommentsMixin:
    """Run comment CRUD requiring ``self.engine: Engine``."""

    engine: Engine

    def add_run_comment(self, run_id: str, author: str, body: str) -> dict:
        with self.engine.begin() as conn:
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
        return dict(row._mapping) if row else {}

    def list_run_comments(self, run_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                run_comments.select()
                .where(run_comments.c.run_id == run_id)
                .order_by(run_comments.c.created_at)
            )
            return [dict(r._mapping) for r in rows]
