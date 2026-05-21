"""Agent-sync mixin: tracks file-system proxy path and sync policy per agent.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``agent_sync``.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import agent_sync


class AgentSyncMixin:
    """File-system sync metadata for agents. Requires ``self.engine: Engine``."""

    engine: Engine

    def get_agent_sync(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_sync.select().where(agent_sync.c.agent_id == agent_id)
            ).first()
            return dict(row._mapping) if row else None

    def upsert_agent_sync(
        self,
        agent_id: str,
        proxy_path: str | None = None,
        sync_mode: str | None = None,
        sync_policy: str | None = None,
        last_file_hash: str | None = None,
        last_file_mtime: str | None = None,
    ) -> dict:
        with self.engine.begin() as conn:
            existing = conn.execute(
                agent_sync.select().where(agent_sync.c.agent_id == agent_id)
            ).first()
            if existing is None:
                conn.execute(
                    agent_sync.insert().values(
                        agent_id=agent_id,
                        proxy_path=proxy_path,
                        sync_mode=sync_mode or "manual",
                        sync_policy=sync_policy or "db_wins",
                        last_file_hash=last_file_hash,
                        last_file_mtime=last_file_mtime,
                        last_sync_at=now_iso(),
                    )
                )
            else:
                values: dict = {"last_sync_at": now_iso()}
                if proxy_path is not None:
                    values["proxy_path"] = proxy_path
                if sync_mode is not None:
                    values["sync_mode"] = sync_mode
                if sync_policy is not None:
                    values["sync_policy"] = sync_policy
                if last_file_hash is not None:
                    values["last_file_hash"] = last_file_hash
                if last_file_mtime is not None:
                    values["last_file_mtime"] = last_file_mtime
                conn.execute(
                    agent_sync.update()
                    .where(agent_sync.c.agent_id == agent_id)
                    .values(**values)
                )
        return self.get_agent_sync(agent_id) or {}

    def delete_agent_sync(self, agent_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(agent_sync.delete().where(agent_sync.c.agent_id == agent_id))
