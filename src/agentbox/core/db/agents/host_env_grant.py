"""AgentHostEnvGrant model + manager — host-env profile grants per agent.

Maps to the ``agent_host_env_grants`` table. Authorization is agent territory;
the workspace owns only availability.
"""
from __future__ import annotations

from typing import Optional, cast

from sqlalchemy import JSON

from sqlmodel import Field

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.tablename import tablename
from agentbox.core.db.base.manager import Manager
from agentbox.core.data.rows import AgentHostEnvGrantRow, HostEnvProfileRow
from agentbox.core.db.schema import agent_host_env_grants, host_env_profiles
from agentbox.core.data._util import now_iso


class AgentHostEnvGrant(Entity, table=True):
	"""A host-env profile linked to an agent with optional overrides."""

	__tablename__ = tablename("agent_host_env_grants")

	agent_id: str = Field(
		primary_key=True, foreign_key="agents.id", ondelete="CASCADE"
	)
	profile_id: Optional[str] = Field(
		foreign_key="host_env_profiles.id", ondelete="SET NULL", default=None,
	)
	overrides: Optional[dict] = Field(default=None, sa_type=JSON)
	changelog: str = Field(nullable=False)
	created_at: str = Field(nullable=False)
	created_by: Optional[str] = Field(default=None)


class AgentHostEnvGrantManager(Manager[AgentHostEnvGrant]):
	"""Manager for the ``agent_host_env_grants`` table."""

	model = AgentHostEnvGrant

	def get_profile(self, profile_id: str) -> HostEnvProfileRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				host_env_profiles.select().where(host_env_profiles.c.id == profile_id)
			).first()
			return cast(HostEnvProfileRow, dict(row._mapping)) if row else None

	def get_grant(self, agent_id: str) -> AgentHostEnvGrantRow | None:
		with self._engine.connect() as conn:
			row = conn.execute(
				agent_host_env_grants.select().where(
					agent_host_env_grants.c.agent_id == agent_id
				)
			).first()
			return cast(AgentHostEnvGrantRow, dict(row._mapping)) if row else None

	def set_grant(
		self,
		agent_id: str,
		*,
		profile_id: str | None,
		overrides: dict | None,
		changelog: str,
		actor: str | None = None,
	) -> AgentHostEnvGrantRow:
		now = now_iso()
		with self._engine.begin() as conn:
			existing = conn.execute(
				agent_host_env_grants.select().where(
					agent_host_env_grants.c.agent_id == agent_id
				)
			).first()
			if existing:
				conn.execute(
					agent_host_env_grants.update()
					.where(agent_host_env_grants.c.agent_id == agent_id)
					.values(
						profile_id=profile_id,
						overrides=overrides,
						changelog=changelog,
						created_at=now,
						created_by=actor,
					)
				)
			else:
				conn.execute(
					agent_host_env_grants.insert().values(
						agent_id=agent_id,
						profile_id=profile_id,
						overrides=overrides,
						changelog=changelog,
						created_at=now,
						created_by=actor,
					)
				)
		result = self.get_grant(agent_id)
		assert result is not None
		return result

	def delete_grant(self, agent_id: str) -> None:
		with self._engine.begin() as conn:
			conn.execute(
				agent_host_env_grants.delete().where(
					agent_host_env_grants.c.agent_id == agent_id
				)
			)
