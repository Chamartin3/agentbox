"""RunCommentManager — run comment CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.comment import RunComment
from agentbox.core.db.schema import run_comments
from agentbox.core.db.utils import now_iso


class RunCommentManager(Manager[RunComment]):
    """Manager for the ``run_comments`` table."""

    model = RunComment

    def add(self, run_id: str, author: str, body: str) -> dict:
        """Insert a comment on a run and return the new row as a dict."""
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
        return dict(row._mapping) if row else {}

    def list_for_run(self, run_id: str) -> list[dict]:
        """List all comments for a run ordered by created_at."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                run_comments.select()
                .where(run_comments.c.run_id == run_id)
                .order_by(run_comments.c.created_at)
            )
            return [dict(r._mapping) for r in rows]
