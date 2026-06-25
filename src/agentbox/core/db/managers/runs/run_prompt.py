"""RunPromptManager — run prompt capture CRUD."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.run_prompt import RunPrompt
from agentbox.core.db.schema import run_prompts
from agentbox.core.db.utils import now_iso


class RunPromptManager(Manager[RunPrompt]):
    """Manager for the ``run_prompts`` table."""

    model = RunPrompt

    def save(self, run_id: str, fragments_json: str) -> None:
        """Upsert the prompt fragments JSON for a run."""
        stmt = sqlite_insert(run_prompts).values(
            run_id=run_id, fragments=fragments_json, created_at=now_iso()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[run_prompts.c.run_id],
            set_={"fragments": stmt.excluded.fragments},
        )
        self._query(stmt)

    def get_fragments(self, run_id: str) -> str | None:
        """Fetch the raw fragments JSON string for a run, or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                select(run_prompts.c.fragments).where(run_prompts.c.run_id == run_id)
            ).first()
            return row[0] if row else None
