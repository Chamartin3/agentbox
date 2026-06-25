"""UsageManager — token usage CRUD + usage aggregates."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.usage import Usage
from agentbox.core.db.schema import usage


class UsageManager(Manager[Usage]):
    """Manager for the ``usage`` table."""

    model = Usage

    def record(self, run_id: str, payload: dict) -> None:
        """Upsert usage for a run, accumulating tokens/cost on conflict."""
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
        self._query(stmt)

    def get_dict(self, run_id: str) -> dict | None:
        """Fetch the usage row for a run as a plain dict, or None."""
        with self._engine.connect() as conn:
            row = conn.execute(usage.select().where(usage.c.run_id == run_id)).first()
            return dict(row._mapping) if row else None

    def aggregate_usage(self) -> dict:
        """Sum tokens + cost across all usage rows, with a run count."""
        stmt = select(
            func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(usage.c.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            func.count().label("runs"),
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        return dict(row._mapping) if row else {}

    def distinct_executors(self) -> list[str]:
        """Distinct reported model values across usage rows, for filter UI."""
        stmt = (
            select(func.coalesce(usage.c.model, "unknown").label("reported_model"))
            .distinct()
            .order_by("reported_model")
        )
        with self._engine.connect() as conn:
            return [r[0] for r in conn.execute(stmt)]
