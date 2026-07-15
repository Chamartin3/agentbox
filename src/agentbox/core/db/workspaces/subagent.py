"""WorkspaceSubagent model and manager — subagent mappings within a workspace.

Maps to the ``workspace_subagents`` table.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Optional, cast

from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs
from agentbox.core.db.schema import workspace_subagents
from agentbox.core.data._util import now_iso
from agentbox.core.data.payload_types import SubagentSpec
from agentbox.core.data.rows import WorkspaceSubagentRow


class WorkspaceSubagent(Entity, table=True):
    """A subagent (agent alias registration) within a workspace."""

    __tablename__ = tablename("workspace_subagents")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    agent_id: str = Field(nullable=False)
    alias: str = Field(nullable=False)
    display_order: int = Field(nullable=False, default=0)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(
        UniqueConstraint("workspace_id", "alias", name="uq_workspace_subagents_alias"),
        Index("ix_workspace_subagents_workspace", "workspace_id"),
    )


class WorkspaceSubagentManager(Manager[WorkspaceSubagent]):
    """Manager for the ``workspace_subagents`` table."""

    model = WorkspaceSubagent

    def list_for_workspace(self, workspace_id: str) -> list[WorkspaceSubagentRow]:
        """Return all subagents for a workspace ordered by display_order."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_subagents.select()
                .where(workspace_subagents.c.workspace_id == workspace_id)
                .order_by(workspace_subagents.c.display_order)
            )
            return [cast(WorkspaceSubagentRow, dict(r._mapping)) for r in rows]

    def replace_for_workspace(
        self,
        workspace_id: str,
        subagents: Iterable[SubagentSpec],
        *,
        actor: str | None = None,
    ) -> list[WorkspaceSubagentRow]:
        """Atomically replace all subagents for a workspace.

        Each dict must have ``agent_id`` and ``alias``; ``display_order``
        defaults to insert-order index.
        """
        now = now_iso()
        rows: list[dict] = []
        seen_aliases: set[str] = set()
        for idx, s in enumerate(subagents):
            agent_id = s.get("agent_id")
            if not agent_id:
                raise ValueError("agent_id is required for subagent bindings")
            alias = (s.get("alias") or "").strip()
            if not alias:
                raise ValueError("alias is required for subagent bindings")
            if alias in seen_aliases:
                raise ValueError(f"Duplicate alias {alias!r} in subagent list")
            seen_aliases.add(alias)
            rows.append(
                {
                    "id": uuid.uuid4().hex,
                    "workspace_id": workspace_id,
                    "agent_id": agent_id,
                    "alias": alias,
                    "display_order": int(s.get("display_order", idx)),
                    "created_at": now,
                    "created_by": actor,
                }
            )
        with self._engine.begin() as conn:
            conn.execute(
                workspace_subagents.delete().where(
                    workspace_subagents.c.workspace_id == workspace_id
                )
            )
            if rows:
                conn.execute(workspace_subagents.insert(), rows)
        return self.list_for_workspace(workspace_id)
