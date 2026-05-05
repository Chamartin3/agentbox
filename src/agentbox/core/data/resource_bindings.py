"""Bindings mixin: agent prompt-embed + workspace file-materialize.

Plans 02 & 03. Both binding tables key off ``resources.id``; one mixin
owns CRUD for both because the editing UX is the same shape (replace
the whole set atomically with a reason).

Public API:

- ``list_prompt_bindings(agent_id)`` /
  ``replace_prompt_bindings(agent_id, bindings, reason)``
- ``list_workspace_file_bindings(workspace_id)`` /
  ``replace_workspace_file_bindings(workspace_id, bindings, reason)``

Each binding dict on input/output has the columns of its table.
Replace operations are atomic (one transaction): delete-all-then-insert.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import (
    agent_prompt_resource_bindings,
    workspace_file_resource_bindings,
    workspace_subagents,
)

VALID_PROMPT_MODES = ("inline", "skill_primer", "name_only", "manifest")
VALID_MATERIALIZE_MODES = ("copy", "symlink", "mount")
VALID_ON_CONFLICT = ("error", "overwrite", "skip")


def _validate_reason(reason: str) -> str:
    if not reason or len(reason.strip()) < 3:
        raise ValueError("reason must be at least 3 characters")
    return reason.strip()


class ResourceBindingsMixin:
    """CRUD for agent prompt-embed + workspace file-materialize bindings."""

    engine: Engine

    # --- prompt bindings (Plan 02) ---

    def list_prompt_bindings(self, agent_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_prompt_resource_bindings.select()
                .where(agent_prompt_resource_bindings.c.agent_id == agent_id)
                .order_by(agent_prompt_resource_bindings.c.display_order)
            )
            return [dict(r._mapping) for r in rows]

    def replace_prompt_bindings(
        self,
        agent_id: str,
        bindings: Iterable[dict],
        *,
        reason: str,
        actor: str | None = None,
    ) -> list[dict]:
        reason = _validate_reason(reason)
        rows = []
        now = now_iso()
        for idx, b in enumerate(bindings):
            mode = b.get("mode")
            if mode not in VALID_PROMPT_MODES:
                raise ValueError(
                    f"Invalid prompt-binding mode {mode!r}; must be one of {VALID_PROMPT_MODES}"
                )
            if not b.get("resource_id") or not b.get("marker"):
                raise ValueError("resource_id and marker are required for prompt bindings")
            rows.append(
                {
                    "id": uuid.uuid4().hex,
                    "agent_id": agent_id,
                    "resource_id": b["resource_id"],
                    "marker": b["marker"],
                    "mode": mode,
                    "pinned_version_id": b.get("pinned_version_id"),
                    "display_order": int(b.get("display_order", idx)),
                    "required": 1 if b.get("required", True) else 0,
                    "changelog": reason,
                    "created_at": now,
                    "created_by": actor,
                }
            )
        with self.engine.begin() as conn:
            conn.execute(
                agent_prompt_resource_bindings.delete().where(
                    agent_prompt_resource_bindings.c.agent_id == agent_id
                )
            )
            if rows:
                conn.execute(agent_prompt_resource_bindings.insert(), rows)
        return self.list_prompt_bindings(agent_id)

    # --- workspace file bindings (Plan 03) ---

    def list_workspace_file_bindings(self, workspace_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                workspace_file_resource_bindings.select()
                .where(workspace_file_resource_bindings.c.workspace_id == workspace_id)
                .order_by(workspace_file_resource_bindings.c.display_order)
            )
            return [dict(r._mapping) for r in rows]

    def count_workspace_file_bindings_by_workspace(self) -> dict[str, int]:
        """Return `{workspace_id: binding_count}` for all workspaces with bindings."""
        from sqlalchemy import func, select

        with self.engine.connect() as conn:
            rows = conn.execute(
                select(
                    workspace_file_resource_bindings.c.workspace_id,
                    func.count().label("n"),
                ).group_by(workspace_file_resource_bindings.c.workspace_id)
            )
            return {r._mapping["workspace_id"]: int(r._mapping["n"]) for r in rows}

    def replace_workspace_file_bindings(
        self,
        workspace_id: str,
        bindings: Iterable[dict],
        *,
        reason: str,
        actor: str | None = None,
    ) -> list[dict]:
        reason = _validate_reason(reason)
        rows = []
        now = now_iso()
        for idx, b in enumerate(bindings):
            mode = b.get("materialize_mode", "copy")
            if mode not in VALID_MATERIALIZE_MODES:
                raise ValueError(
                    f"Invalid materialize_mode {mode!r}; must be one of {VALID_MATERIALIZE_MODES}"
                )
            on_conflict = b.get("on_conflict", "error")
            if on_conflict not in VALID_ON_CONFLICT:
                raise ValueError(
                    f"Invalid on_conflict {on_conflict!r}; must be one of {VALID_ON_CONFLICT}"
                )
            if not b.get("resource_id"):
                raise ValueError("resource_id is required for workspace bindings")
            target_path = b.get("target_path")
            if target_path and ".." in target_path.split("/"):
                raise ValueError(
                    f"target_path {target_path!r} must not contain '..' segments"
                )
            rows.append(
                {
                    "id": uuid.uuid4().hex,
                    "workspace_id": workspace_id,
                    "resource_id": b["resource_id"],
                    "target_path": target_path,
                    "pinned_version_id": b.get("pinned_version_id"),
                    "materialize_mode": mode,
                    "on_conflict": on_conflict,
                    "display_order": int(b.get("display_order", idx)),
                    "changelog": reason,
                    "created_at": now,
                    "created_by": actor,
                }
            )
        with self.engine.begin() as conn:
            conn.execute(
                workspace_file_resource_bindings.delete().where(
                    workspace_file_resource_bindings.c.workspace_id == workspace_id
                )
            )
            if rows:
                conn.execute(workspace_file_resource_bindings.insert(), rows)
        return self.list_workspace_file_bindings(workspace_id)

    # --- workspace subagents (RESOURCES_PLAN Phase 2) ---

    def list_workspace_subagents(self, workspace_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                workspace_subagents.select()
                .where(workspace_subagents.c.workspace_id == workspace_id)
                .order_by(workspace_subagents.c.display_order)
            )
            return [dict(r._mapping) for r in rows]

    def replace_workspace_subagents(
        self,
        workspace_id: str,
        subagents: Iterable[dict],
        *,
        actor: str | None = None,
    ) -> list[dict]:
        now = now_iso()
        rows = []
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
        with self.engine.begin() as conn:
            conn.execute(
                workspace_subagents.delete().where(
                    workspace_subagents.c.workspace_id == workspace_id
                )
            )
            if rows:
                conn.execute(workspace_subagents.insert(), rows)
        return self.list_workspace_subagents(workspace_id)
