"""UsageManager — token usage CRUD + usage aggregates."""
from __future__ import annotations

from sqlalchemy import func, select

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.usage import Usage
from agentbox.core.db.schema import usage


class UsageManager(Manager[Usage]):
    """Manager for the ``usage`` table."""

    model = Usage

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
