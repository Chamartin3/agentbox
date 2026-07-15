"""AgentConfigEvent model + manager — configuration change tracking for agents.

Maps to the ``agent_config_events`` table.
"""
from __future__ import annotations

from typing import Optional, Unpack

from sqlalchemy import Row

from agentbox.core.db.base.tablename import tablename, tableargs
from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.data.rows import AgentConfigEventRow, _AgentConfigEventFields


class AgentConfigEvent(Entity, table=True):
	"""Audit log of configuration changes to an agent definition."""

	__tablename__ = tablename("agent_config_events")

	id: int = Field(default=None, primary_key=True)
	agent_id: str = Field(nullable=False)
	field: str = Field(nullable=False)
	from_value: Optional[str] = Field(default=None)
	to_value: Optional[str] = Field(default=None)
	author: str = Field(nullable=False)
	source: str = Field(nullable=False)
	created_at: str = Field(nullable=False)

	__table_args__ = tableargs(
		Index("ix_agent_config_events_agent", "agent_id"),
		Index("ix_agent_config_events_created", "created_at"),
	)


agent_config_events = AgentConfigEvent.__table__


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
