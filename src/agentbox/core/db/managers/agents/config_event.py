"""AgentConfigEventManager — agent config change audit log (pure row ops).

Value serialization (JSON-encoding from/to) and the ``created_at`` timestamp
are policy → ``AgentService``; these methods only insert/read rows.
"""
from __future__ import annotations

from typing import Unpack

from sqlalchemy import Row

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.config_event import AgentConfigEvent
from agentbox.core.data.rows import AgentConfigEventRow, _AgentConfigEventFields
from agentbox.core.db.schema import agent_config_events


def _event_row(row: Row) -> AgentConfigEventRow:
    """Shape an ``agent_config_events`` row into the ``AgentConfigEventRow`` contract."""
    m = row._mapping
    return AgentConfigEventRow(
        id=m["id"],
        agent_id=m["agent_id"],
        field=m["field"],
        from_value=m["from_value"],
        to_value=m["to_value"],
        author=m["author"],
        source=m["source"],
        created_at=m["created_at"],
    )


class AgentConfigEventManager(Manager[AgentConfigEvent]):
    """Manager for the ``agent_config_events`` table — pure row ops."""
    model = AgentConfigEvent

    def insert(self, **fields: Unpack[_AgentConfigEventFields]) -> int:
        """Insert a config event row and return the new auto-incremented id."""
        with self._engine.begin() as conn:
            result = conn.execute(agent_config_events.insert().values(**fields))
            pk = result.inserted_primary_key
            assert pk is not None
            return int(pk[0])

    def get_by_id(self, event_id: int) -> AgentConfigEventRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                agent_config_events.select().where(agent_config_events.c.id == event_id)
            ).first()
            return _event_row(row) if row else None

    def list_for_agent(self, agent_id: str, limit: int = 50) -> list[AgentConfigEventRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                agent_config_events.select()
                .where(agent_config_events.c.agent_id == agent_id)
                .order_by(agent_config_events.c.created_at.desc())  # sqlalchemy: Column.desc() not in stubs
                .limit(limit)
            )
            return [_event_row(r) for r in rows.fetchall()]
