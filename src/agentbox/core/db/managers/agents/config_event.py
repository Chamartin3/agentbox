"""AgentConfigEventManager — agent config change audit log (pure row ops).

Value serialization (JSON-encoding from/to) and the ``created_at`` timestamp
are policy → ``AgentService``; these methods only insert/read rows.
"""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.config_event import AgentConfigEvent
from agentbox.core.db.schema import agent_config_events


class AgentConfigEventManager(Manager[AgentConfigEvent]):
    """Manager for the ``agent_config_events`` table — pure row ops."""
    model = AgentConfigEvent

    def insert(self, **fields: object) -> None:
        with self._engine.begin() as conn:
            conn.execute(agent_config_events.insert().values(**fields))

    def list_for_agent(self, agent_id: str, limit: int = 50) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                agent_config_events.select()
                .where(agent_config_events.c.agent_id == agent_id)
                .order_by(agent_config_events.c.created_at.desc())  # sqlalchemy: Column.desc() not in stubs
                .limit(limit)
            )
            return [dict(r._mapping) for r in rows]
