"""PromptVersionManager — prompt version history CRUD (pure row ops).

Draft/publish/rollback policy (hashing, timestamps, changelog composition,
draft/committed guards) lives in ``AgentService``; these methods only touch
the ``prompt_versions`` table. The version-number computation stays inside
the atomic writes here because it must observe the same transaction that
deletes the prior draft (legacy ``save_prompt_draft`` reused the draft's
number by computing max *after* the delete).
"""
from __future__ import annotations

from sqlalchemy import func, select

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.prompt import PromptVersion
from agentbox.core.db.schema import prompt_versions


class PromptVersionManager(Manager[PromptVersion]):
    """Manager for the ``prompt_versions`` table — pure row ops."""
    model = PromptVersion

    # ── reads ──────────────────────────────────────────────────────────
    def list_for_agent(self, agent_id: str) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                prompt_versions.select()
                .where(prompt_versions.c.agent_id == agent_id)
                .order_by(prompt_versions.c.version.desc())
            )
            return [dict(r._mapping) for r in rows]

    def get_by_number(self, agent_id: str, version: int) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                prompt_versions.select().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.version == version,
                )
            ).first()
            return dict(row._mapping) if row else None

    def get_latest_committed(self, agent_id: str) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                prompt_versions.select()
                .where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 0,
                )
                .order_by(prompt_versions.c.version.desc())
                .limit(1)
            ).first()
            return dict(row._mapping) if row else None

    def get_draft(self, agent_id: str) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                prompt_versions.select()
                .where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 1,
                )
                .order_by(prompt_versions.c.version.desc())
                .limit(1)
            ).first()
            return dict(row._mapping) if row else None

    # ── writes ─────────────────────────────────────────────────────────
    def replace_draft(
        self,
        agent_id: str,
        *,
        content: str,
        content_hash: str,
        author: str,
        changelog: str,
        created_at: str,
    ) -> dict:
        """Atomically drop the agent's draft and insert a fresh one.

        Next version is computed *after* the delete (in-txn) so the freed
        slot is reused, matching the legacy single-draft semantics.
        """
        with self._engine.begin() as conn:
            conn.execute(
                prompt_versions.delete().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 1,
                )
            )
            version = _next_version(conn, agent_id)
            conn.execute(
                prompt_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
                    content=content,
                    author=author,
                    changelog=changelog,
                    is_draft=1,
                    content_hash=content_hash,
                    created_at=created_at,
                )
            )
            row = conn.execute(
                prompt_versions.select().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.version == version,
                )
            ).first()
            return dict(row._mapping) if row else {}

    def insert_committed(
        self,
        agent_id: str,
        *,
        content: str,
        content_hash: str,
        author: str,
        changelog: str,
        created_at: str,
        delete_drafts: bool = False,
    ) -> dict:
        """Insert a committed (non-draft) version, computing the next number
        in-txn. Optionally drops any existing draft first (rollback path)."""
        with self._engine.begin() as conn:
            if delete_drafts:
                conn.execute(
                    prompt_versions.delete().where(
                        prompt_versions.c.agent_id == agent_id,
                        prompt_versions.c.is_draft == 1,
                    )
                )
            version = _next_version(conn, agent_id)
            conn.execute(
                prompt_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
                    content=content,
                    author=author,
                    changelog=changelog,
                    is_draft=0,
                    content_hash=content_hash,
                    created_at=created_at,
                )
            )
            row = conn.execute(
                prompt_versions.select().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.version == version,
                )
            ).first()
            return dict(row._mapping) if row else {}

    def patch(self, version_id: int, **values: object) -> None:
        """Update the supplied columns on one prompt-version row."""
        with self._engine.begin() as conn:
            conn.execute(
                prompt_versions.update()
                .where(prompt_versions.c.id == version_id)
                .values(**values)
            )


def _next_version(conn: object, agent_id: str) -> int:
    """Max(version)+1 for an agent, evaluated on the given connection."""
    row = conn.execute(  # type: ignore[attr-defined]
        select(func.coalesce(func.max(prompt_versions.c.version), 0)).where(
            prompt_versions.c.agent_id == agent_id
        )
    ).first()
    return int(row[0]) + 1 if row else 1
