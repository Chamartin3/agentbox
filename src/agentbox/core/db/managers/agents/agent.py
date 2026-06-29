"""Agent, ActiveAgentVersion, AgentMeta and AgentRunnerProfile managers."""
from __future__ import annotations

from typing import Unpack

from sqlalchemy import Row

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.agent import (
    ActiveAgentVersion,
    Agent,
    AgentMeta,
    AgentRunnerProfile,
)
from agentbox.core.data.rows import AgentMetaRow, _AgentMetaFields, _AgentMetaPatchFields
from agentbox.core.db.schema import active_agent_versions, agent_meta


def _meta_row(row: Row) -> AgentMetaRow:
    """Shape an ``agent_meta`` row into the ``AgentMetaRow`` contract."""
    m = row._mapping
    return AgentMetaRow(
        agent_id=m["agent_id"],
        sync_mode=m["sync_mode"],
        export_to_disk=m["export_to_disk"],
        source_path=m["source_path"],
        source_format=m["source_format"],
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
