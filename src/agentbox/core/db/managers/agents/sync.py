"""AgentSyncManager — manifest-to-DB sync metadata CRUD (pure row ops).

Upsert branching (insert-vs-update, default sync_mode/policy) and the
``last_sync_at`` timestamp are policy → ``AgentService``; these methods
only read/insert/patch/delete the ``agent_sync`` row.
"""
from __future__ import annotations

from sqlalchemy import Row

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.sync import AgentSync
from agentbox.core.db.row_types import AgentSyncRow
from agentbox.core.db.schema import agent_sync


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

    def insert(self, **fields: object) -> None:
        with self._engine.begin() as conn:
            conn.execute(agent_sync.insert().values(**fields))

    def patch(self, agent_id: str, **values: object) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                agent_sync.update()
                .where(agent_sync.c.agent_id == agent_id)
                .values(**values)
            )

    def delete_for_agent(self, agent_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(agent_sync.delete().where(agent_sync.c.agent_id == agent_id))
