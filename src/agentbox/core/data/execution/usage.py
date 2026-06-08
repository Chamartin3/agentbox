"""Usage CRUD mixin."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from agentbox.core.data.schema import usage


class UsageMixin:
    """Usage CRUD requiring ``self.engine: Engine``."""

    engine: Engine

    def record_usage(self, run_id: str, payload: dict) -> None:
        values = {
            "run_id": run_id,
            "model": payload.get("model"),
            "input_tokens": payload.get("input_tokens", 0),
            "output_tokens": payload.get("output_tokens", 0),
            "cache_read_tokens": payload.get("cache_read_tokens", 0),
            "cache_write_tokens": payload.get("cache_write_tokens", 0),
            "cost_usd": payload.get("cost_usd"),
        }
        stmt = sqlite_insert(usage).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[usage.c.run_id],
            set_={
                "model": func.coalesce(stmt.excluded.model, usage.c.model),
                "input_tokens": usage.c.input_tokens + stmt.excluded.input_tokens,
                "output_tokens": usage.c.output_tokens + stmt.excluded.output_tokens,
                "cache_read_tokens": usage.c.cache_read_tokens
                + stmt.excluded.cache_read_tokens,
                "cache_write_tokens": usage.c.cache_write_tokens
                + stmt.excluded.cache_write_tokens,
                "cost_usd": func.coalesce(usage.c.cost_usd, 0)
                + func.coalesce(stmt.excluded.cost_usd, 0),
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_usage(self, run_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(usage.select().where(usage.c.run_id == run_id)).first()
            return dict(row._mapping) if row else None
