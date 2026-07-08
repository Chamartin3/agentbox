"""AgentHostEnvGrantManager — agent-scoped host-env grant CRUD.

Authorization is agent territory: host-env grants are keyed on the agent, not
the workspace. Named grant bundles live in the shared ``host_env_profiles``
table (read here for resolution).
"""
from __future__ import annotations

from typing import cast

from agentbox.core.data.rows import AgentHostEnvGrantRow, HostEnvProfileRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.host_env_grant import AgentHostEnvGrant
from agentbox.core.db.schema import agent_host_env_grants, host_env_profiles
from agentbox.core.db.utils import now_iso


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
