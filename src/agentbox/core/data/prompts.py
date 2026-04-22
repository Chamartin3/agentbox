"""Prompt-versions mixin: draft / publish / rollback queries.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``prompt_versions`` only — independent of run state.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import prompt_versions


class PromptVersionsMixin:
    """Versioned prompt persistence. Requires ``self.engine: Engine``."""

    engine: Engine

    def list_prompt_versions(self, agent_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                prompt_versions.select()
                .where(prompt_versions.c.agent_id == agent_id)
                .order_by(prompt_versions.c.version.desc())
            )
            return [dict(r._mapping) for r in rows]

    def get_prompt_version(self, agent_id: str, version: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                prompt_versions.select().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.version == version,
                )
            ).first()
            return dict(row._mapping) if row else None

    def get_latest_committed_prompt(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
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

    def get_prompt_draft(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
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

    def _next_prompt_version(self, agent_id: str) -> int:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(func.coalesce(func.max(prompt_versions.c.version), 0)).where(
                    prompt_versions.c.agent_id == agent_id
                )
            ).first()
            return int(row[0]) + 1 if row else 1

    def save_prompt_draft(
        self, agent_id: str, content: str, author: str = "system"
    ) -> dict:
        """Save or update the draft for an agent."""
        with self.engine.begin() as conn:
            conn.execute(
                prompt_versions.delete().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 1,
                )
            )
            version = self._next_prompt_version(agent_id)
            conn.execute(
                prompt_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
                    content=content,
                    author=author,
                    changelog="",
                    is_draft=1,
                    created_at=now_iso(),
                )
            )
        return self.get_prompt_draft(agent_id) or {}

    def publish_prompt(
        self, agent_id: str, changelog: str = "", author: str = "system"
    ) -> dict:
        """Publish the current draft as a committed version."""
        draft = self.get_prompt_draft(agent_id)
        if not draft:
            raise ValueError(f"No draft found for agent {agent_id!r}")

        with self.engine.begin() as conn:
            conn.execute(
                prompt_versions.update()
                .where(prompt_versions.c.id == draft["id"])
                .values(
                    is_draft=0,
                    changelog=changelog,
                    created_at=now_iso(),
                )
            )
        return self.get_prompt_version(agent_id, draft["version"]) or {}

    def rollback_prompt(
        self, agent_id: str, target_version: int, author: str = "system"
    ) -> dict:
        """Create a new version copying the content of target_version."""
        target = self.get_prompt_version(agent_id, target_version)
        if not target:
            raise ValueError(
                f"Version {target_version} not found for agent {agent_id!r}"
            )
        if target["is_draft"]:
            raise ValueError(f"Cannot rollback to a draft version ({target_version})")

        with self.engine.begin() as conn:
            conn.execute(
                prompt_versions.delete().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 1,
                )
            )
            version = self._next_prompt_version(agent_id)
            conn.execute(
                prompt_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
                    content=target["content"],
                    author=author,
                    changelog=f"Rollback to version {target_version}",
                    is_draft=0,
                    created_at=now_iso(),
                )
            )
        return self.get_latest_committed_prompt(agent_id) or {}
