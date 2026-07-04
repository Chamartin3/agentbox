"""WorkspaceSubagentManager — subagent registration CRUD."""
from __future__ import annotations

from agentbox.core.data.payload_types import SubagentSpec

import uuid
from collections.abc import Iterable
from typing import cast

from agentbox.core.data.rows import WorkspaceSubagentRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.subagent import WorkspaceSubagent
from agentbox.core.db.schema import workspace_subagents
from agentbox.core.db.utils import now_iso


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
