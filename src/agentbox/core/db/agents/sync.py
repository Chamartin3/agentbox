"""AgentSync model + manager — manifest-to-DB sync metadata.

Maps to the ``agent_sync`` table.
"""
from __future__ import annotations

from typing import Optional, Unpack

from sqlalchemy import Row

from agentbox.core.db.base.tablename import tablename
from sqlmodel import Field

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.data.rows import AgentSyncRow, _AgentSyncFields, _AgentSyncPatchFields


class AgentSync(Entity, table=True):
	"""Sync tracking metadata for an agent definition between manifest and DB."""

	__tablename__ = tablename("agent_sync")

	agent_id: str = Field(primary_key=True)
	proxy_path: Optional[str] = Field(default=None)
	sync_mode: str = Field(nullable=False, default="manual", sa_column_kwargs={"server_default": "manual"})
	sync_policy: str = Field(nullable=False, default="db_wins", sa_column_kwargs={"server_default": "db_wins"})
	last_file_hash: Optional[str] = Field(default=None)
	last_file_mtime: Optional[str] = Field(default=None)
	last_sync_at: Optional[str] = Field(default=None)


agent_sync = AgentSync.__table__


def _sync_row(row: Row) -> AgentSyncRow:
	"""Shape an ``agent_sync`` row into the ``AgentSyncRow`` contract."""
	m = row._mapping
	return AgentSyncRow(
		agent_id=m["agent_id"],
		proxy_path=m["proxy_path"],
		sync_mode=m["sync_mode"],
		sync_policy=m["sync_policy"],
		last_file_hash=m["last_file_hash"],
		last_file_mtime=m["last_file_mtime"],
		last_sync_at=m["last_sync_at"],
	)


class AgentSyncManager(Manager[AgentSync]):
	"""Manager for the ``agent_sync`` table — pure row ops."""
	model = AgentSync

	def get_row(self, agent_id: str) -> AgentSyncRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_sync.select().where(agent_sync.c.agent_id == agent_id)
			).first()
			return _sync_row(row) if row else None

	def insert(self, **fields: Unpack[_AgentSyncFields]) -> None:
		with self._engine.begin() as conn:
			conn.execute(agent_sync.insert().values(**fields))

	def patch(self, agent_id: str, **values: Unpack[_AgentSyncPatchFields]) -> None:
		with self._engine.begin() as conn:
			conn.execute(
				agent_sync.update()
				.where(agent_sync.c.agent_id == agent_id)
				.values(**values)
			)

	def delete_for_agent(self, agent_id: str) -> None:
		with self._engine.begin() as conn:
			conn.execute(agent_sync.delete().where(agent_sync.c.agent_id == agent_id))
