"""Agent identity models + managers — agent, active_agent_versions, agent_meta.

Maps to the ``agents``, ``active_agent_versions``, and ``agent_meta`` tables.
"""
from __future__ import annotations

from typing import Optional, Unpack

from sqlalchemy import Row

from agentbox.core.db.base.tablename import tablename
from sqlmodel import Field

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.data.rows import AgentMetaRow, _AgentMetaFields, _AgentMetaPatchFields


class Agent(Entity, table=True):
	"""Canonical agent identity. Minimal record — metadata lives in ``AgentMeta``."""

	__tablename__ = tablename("agents")

	id: str = Field(primary_key=True)
	name: str = Field(nullable=False)
	created_at: str = Field(nullable=False)


class ActiveAgentVersion(Entity, table=True):
	"""Points to the currently active version for each agent."""

	__tablename__ = tablename("active_agent_versions")

	agent_id: str = Field(primary_key=True)
	version_id: int = Field(foreign_key="agent_versions.id", nullable=False)
	activated_at: str = Field(nullable=False)


class AgentMeta(Entity, table=True):
	"""Agent metadata — sync mode, source path, lifecycle timestamps."""

	__tablename__ = tablename("agent_meta")

	agent_id: str = Field(primary_key=True)
	sync_mode: str = Field(nullable=False, default="off", sa_column_kwargs={"server_default": "off"})
	export_to_disk: int = Field(nullable=False, default=0, sa_column_kwargs={"server_default": "0"})
	source_path: Optional[str] = Field(default=None)
	created_at: str = Field(nullable=False)
	updated_at: str = Field(nullable=False)
	deleted_at: Optional[str] = Field(default=None)
	disabled_at: Optional[str] = Field(default=None)


class AgentRunnerProfile(Entity, table=True):
	"""Maps an agent to its active runner profile."""

	__tablename__ = tablename("agent_runner_profiles")

	agent_id: str = Field(primary_key=True)
	runner_profile_id: str = Field(foreign_key="runner_profiles.id", nullable=False)
	created_at: str = Field(nullable=False)
	updated_at: str = Field(nullable=False)


active_agent_versions = ActiveAgentVersion.__table__
agent_meta = AgentMeta.__table__


def _meta_row(row: Row) -> AgentMetaRow:
	"""Shape an ``agent_meta`` row into the ``AgentMetaRow`` contract."""
	m = row._mapping
	return AgentMetaRow(
		agent_id=m["agent_id"],
		sync_mode=m["sync_mode"],
		export_to_disk=m["export_to_disk"],
		source_path=m["source_path"],
		created_at=m["created_at"],
		updated_at=m["updated_at"],
		deleted_at=m["deleted_at"],
		disabled_at=m["disabled_at"],
	)


class AgentManager(Manager[Agent]):
	"""Manager for the ``agents`` table."""
	model = Agent


class ActiveAgentVersionManager(Manager[ActiveAgentVersion]):
	"""Manager for the ``active_agent_versions`` table."""
	model = ActiveAgentVersion

	def delete_for_agent(self, agent_id: str) -> None:
		"""Delete the active-version pointer for an agent."""
		with self._engine.begin() as conn:
			conn.execute(
				active_agent_versions.delete().where(
					active_agent_versions.c.agent_id == agent_id
				)
			)

	def set_pointer(self, agent_id: str, version_id: int, activated_at: str) -> None:
		"""Atomically replace the active pointer (delete + insert in one txn)."""
		with self._engine.begin() as conn:
			conn.execute(
				active_agent_versions.delete().where(
					active_agent_versions.c.agent_id == agent_id
				)
			)
			conn.execute(
				active_agent_versions.insert().values(
					agent_id=agent_id,
					version_id=version_id,
					activated_at=activated_at,
				)
			)


class AgentMetaManager(Manager[AgentMeta]):
	"""Manager for the ``agent_meta`` table — pure row ops.

	Lifecycle policy (guards, timestamps, active-pointer clearing) lives in
	``AgentService``; these just read/insert/patch the row.
	"""
	model = AgentMeta

	def get_meta(self, agent_id: str) -> AgentMetaRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_meta.select().where(agent_meta.c.agent_id == agent_id)
			).first()
			return _meta_row(row) if row else None

	def insert(self, **fields: Unpack[_AgentMetaFields]) -> None:
		with self._engine.begin() as conn:
			conn.execute(agent_meta.insert().values(**fields))

	def patch(self, agent_id: str, **values: Unpack[_AgentMetaPatchFields]) -> None:
		"""Update the supplied columns on an existing meta row."""
		with self._engine.begin() as conn:
			conn.execute(
				agent_meta.update()
				.where(agent_meta.c.agent_id == agent_id)
				.values(**values)
			)

	def agent_ids_with_deleted(self) -> set[str]:
		"""Agent ids whose meta row carries a ``deleted_at`` timestamp."""
		with self._engine.connect() as conn:
			return {
				r._mapping["agent_id"]
				for r in conn.execute(
					agent_meta.select().where(agent_meta.c.deleted_at.isnot(None))  # sqlalchemy: Column.isnot() not in stubs
				)
			}

	def agent_ids_with_disabled(self) -> set[str]:
		"""Agent ids whose meta row carries a ``disabled_at`` timestamp."""
		with self._engine.connect() as conn:
			return {
				r._mapping["agent_id"]
				for r in conn.execute(
					agent_meta.select().where(agent_meta.c.disabled_at.isnot(None))  # sqlalchemy: Column.isnot() not in stubs
				)
			}


class AgentRunnerProfileManager(Manager[AgentRunnerProfile]):
	"""Manager for the ``agent_runner_profiles`` table."""
	model = AgentRunnerProfile
