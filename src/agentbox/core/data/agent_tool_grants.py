"""Mixin for agent-scoped tool grant CRUD (Plan 19)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import agent_tool_grants


class AgentToolGrantsMixin:
    """CRUD for agent_tool_grants rows. Mixed into SessionStore."""

    def grant_agent_tool(
        self,
        agent_id: str,
        tool_name: str,
        changelog: str,
        actor: str | None = None,
    ) -> dict:
        """Grant a tool to an agent. Re-activates a previously revoked grant."""
        if len(changelog.strip()) < 3:
            raise ValueError("changelog must be at least 3 characters")

        now = now_iso()
        with self.engine.begin() as conn:
            existing = (
                conn.execute(
                    select(agent_tool_grants).where(
                        agent_tool_grants.c.agent_id == agent_id,
                        agent_tool_grants.c.tool_name == tool_name,
                    )
                )
                .mappings()
                .first()
            )

            if existing is None:
                row_id = str(uuid.uuid4())
                conn.execute(
                    agent_tool_grants.insert().values(
                        id=row_id,
                        agent_id=agent_id,
                        tool_name=tool_name,
                        changelog=changelog,
                        granted_at=now,
                        granted_by=actor,
                        revoked_at=None,
                        revoked_by=None,
                        revoke_changelog=None,
                    )
                )
            else:
                row_id = existing["id"]
                conn.execute(
                    update(agent_tool_grants)
                    .where(agent_tool_grants.c.id == row_id)
                    .values(
                        changelog=changelog,
                        granted_at=now,
                        granted_by=actor,
                        revoked_at=None,
                        revoked_by=None,
                        revoke_changelog=None,
                    )
                )

        return self._get_grant_row(agent_id, tool_name)

    def revoke_agent_tool(
        self,
        agent_id: str,
        tool_name: str,
        changelog: str,
        actor: str | None = None,
    ) -> None:
        """Soft-revoke a grant. Sets revoked_at; row is preserved for audit."""
        if len(changelog.strip()) < 3:
            raise ValueError("changelog must be at least 3 characters")

        now = now_iso()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(agent_tool_grants)
                .where(
                    agent_tool_grants.c.agent_id == agent_id,
                    agent_tool_grants.c.tool_name == tool_name,
                    agent_tool_grants.c.revoked_at.is_(None),
                )
                .values(
                    revoked_at=now,
                    revoked_by=actor,
                    revoke_changelog=changelog,
                )
            )
            if result.rowcount == 0:
                raise ValueError(
                    f"No active grant for agent {agent_id!r} / tool {tool_name!r}"
                )

    def list_agent_tool_grants(
        self,
        agent_id: str,
        include_revoked: bool = False,
    ) -> list[dict]:
        """Return grant rows for an agent, newest-first."""
        with self.engine.connect() as conn:
            q = select(agent_tool_grants).where(
                agent_tool_grants.c.agent_id == agent_id
            )
            if not include_revoked:
                q = q.where(agent_tool_grants.c.revoked_at.is_(None))
            q = q.order_by(agent_tool_grants.c.granted_at.desc())
            rows = conn.execute(q).mappings().all()
            return [dict(r) for r in rows]

    def list_active_grants(self, agent_id: str) -> set[str]:
        """Return set of active tool_names for an agent. Used by executor at run-start."""
        rows = self.list_agent_tool_grants(agent_id, include_revoked=False)
        return {r["tool_name"] for r in rows}

    def _get_grant_row(self, agent_id: str, tool_name: str) -> dict:
        with self.engine.connect() as conn:
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
            if row is None:
                raise RuntimeError("grant row missing after write")
            return dict(row)
