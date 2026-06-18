"""Agent config event log — records non-versioned field changes."""

from __future__ import annotations

import json
import warnings

from sqlalchemy.engine import Engine

from agentbox.core.db.utils import now_iso
from agentbox.core.db.schema import agent_config_events


class AgentConfigEventsMixin:
    """Config event persistence. Requires ``self.engine: Engine``.

    .. deprecated::
        Use ``Database.agent_config_events`` manager methods instead.
    """

    engine: Engine

    def record_config_event(
        self,
        agent_id: str,
        field: str,
        from_value: object,
        to_value: object,
        author: str = "api",
        source: str = "api:patch",
    ) -> dict:
        warnings.warn(
            "AgentConfigEventsMixin.record_config_event is deprecated; use db.agent_config_events.create(...)",
            DeprecationWarning,
            stacklevel=2,
        )
        row = {
            "agent_id": agent_id,
            "field": field,
            "from_value": json.dumps(from_value) if from_value is not None else None,
            "to_value": json.dumps(to_value) if to_value is not None else None,
            "author": author,
            "source": source,
            "created_at": now_iso(),
        }
        with self.engine.begin() as conn:
            conn.execute(agent_config_events.insert().values(**row))
        return row

    def list_config_events(self, agent_id: str, limit: int = 50) -> list[dict]:
        warnings.warn(
            "AgentConfigEventsMixin.list_config_events is deprecated; use db.agent_config_events.find(agent_id=...)",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_config_events.select()
                .where(agent_config_events.c.agent_id == agent_id)
                .order_by(agent_config_events.c.created_at.desc())
                .limit(limit)
            )
            return [dict(r._mapping) for r in rows]
