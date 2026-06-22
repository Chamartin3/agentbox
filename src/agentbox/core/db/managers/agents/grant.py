"""AgentToolGrantManager — tool permission grant CRUD."""
from __future__ import annotations

from sqlalchemy import select, update as sa_update

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.grant import AgentToolGrant
from agentbox.core.db.schema import agent_tool_grants


class AgentToolGrantManager(Manager[AgentToolGrant]):
    """Manager for the ``agent_tool_grants`` table — pure row ops.

    Policy (changelog validation, id generation, reactivate-vs-insert,
    revoke-missing handling) lives in ``AgentService``.
    """
    model = AgentToolGrant

    def get_grant(self, agent_id: str, tool_name: str) -> dict | None:
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    select(agent_tool_grants).where(
                        agent_tool_grants.c.agent_id == agent_id,
                        agent_tool_grants.c.tool_name == tool_name,
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def list_for_agent(self, agent_id: str, include_revoked: bool = False) -> list[dict]:
        with self._engine.connect() as conn:
            q = select(agent_tool_grants).where(agent_tool_grants.c.agent_id == agent_id)
            if not include_revoked:
                q = q.where(agent_tool_grants.c.revoked_at.is_(None))  # sqlalchemy: Column.is_() not in stubs
            q = q.order_by(agent_tool_grants.c.granted_at.desc())
            return [dict(r) for r in conn.execute(q).mappings().all()]

    def insert(self, **fields: object) -> None:
        with self._engine.begin() as conn:
            conn.execute(agent_tool_grants.insert().values(**fields))

    def update_by_id(self, row_id: str, **values: object) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sa_update(agent_tool_grants)
                .where(agent_tool_grants.c.id == row_id)
                .values(**values)
            )

    def revoke_active(self, agent_id: str, tool_name: str, **values: object) -> int:
        """Soft-revoke the active grant; returns rows affected (0 if none)."""
        with self._engine.begin() as conn:
            result = conn.execute(
                sa_update(agent_tool_grants)
                .where(
                    agent_tool_grants.c.agent_id == agent_id,
                    agent_tool_grants.c.tool_name == tool_name,
                    agent_tool_grants.c.revoked_at.is_(None),  # sqlalchemy: Column.is_() not in stubs
                )
                .values(**values)
            )
            return result.rowcount
