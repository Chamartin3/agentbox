"""Run prompt CRUD mixin."""

from __future__ import annotations

import warnings

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from agentbox.core.db.schema import run_prompts
from agentbox.core.db.utils import now_iso


class RunPromptsMixin:
    """Run prompt CRUD requiring ``self.engine: Engine``."""

    engine: Engine

    def save_run_prompt(self, run_id: str, fragments_json: str) -> None:
        stmt = sqlite_insert(run_prompts).values(
            run_id=run_id, fragments=fragments_json, created_at=now_iso()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[run_prompts.c.run_id],
            set_={"fragments": stmt.excluded.fragments},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_run_prompt(self, run_id: str) -> str | None:
        warnings.warn(
            "RunPromptsMixin.get_run_prompt is deprecated; use db.run_prompts manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                select(run_prompts.c.fragments).where(run_prompts.c.run_id == run_id)
            ).first()
            return row[0] if row else None
