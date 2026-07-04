"""AgentPromptResourceBinding and WorkspaceFileResourceBinding managers."""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import cast

from sqlalchemy import func, select

from agentbox.core.constants import MaterializeMode, OnConflict, PromptMode, PromptSlot
from agentbox.core.data.rows import AgentPromptBindingRow, WorkspaceFileBindingRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.resources.binding import (
    AgentPromptResourceBinding,
    WorkspaceFileResourceBinding,
)
from agentbox.core.db.schema import (
    agent_prompt_resource_bindings,
    resources as resources_table,
    workspace_file_resource_bindings,
)
from agentbox.core.db.utils import now_iso


_MIN_REASON = 3


def _validate_reason(reason: str) -> str:
    if not reason or len(reason.strip()) < _MIN_REASON:
        raise ValueError("reason must be at least 3 characters")
    return reason.strip()


# ---------------------------------------------------------------------------
# AgentPromptResourceBindingManager
# ---------------------------------------------------------------------------


class AgentPromptResourceBindingManager(Manager[AgentPromptResourceBinding]):
    """Manager for the ``agent_prompt_resource_bindings`` table."""

    model = AgentPromptResourceBinding

    def list_for_agent(self, agent_id: str) -> list[AgentPromptBindingRow]:
        """Return all prompt bindings for an agent ordered by display_order."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                agent_prompt_resource_bindings.select()
                .where(agent_prompt_resource_bindings.c.agent_id == agent_id)
                .order_by(agent_prompt_resource_bindings.c.display_order)
            )
            return [cast(AgentPromptBindingRow, dict(r._mapping)) for r in rows]

    def replace_for_agent(
        self,
        agent_id: str,
        bindings: Iterable[dict],
        *,
        reason: str,
        actor: str | None = None,
    ) -> list[AgentPromptBindingRow]:
        """Atomically replace all prompt bindings for an agent."""
        reason = _validate_reason(reason)
        rows: list[dict] = []
        now = now_iso()
        slots_seen: set[str] = set()
        bindings = list(bindings)
        for idx, b in enumerate(bindings):
            if not b.get("resource_id"):
                raise ValueError("resource_id is required for prompt bindings")
            slot = b.get("slot")
            mode = b.get("mode")
            marker = b.get("marker")
            if slot is not None:
                PromptSlot.coerce(slot, label="prompt-binding slot")
                if slot in slots_seen:
                    raise ValueError(
                        f"Duplicate prompt-binding slot {slot!r} for agent {agent_id!r}"
                    )
                slots_seen.add(slot)
                marker = marker or None
                mode = mode or None
            else:
                if marker:
                    PromptMode.coerce(mode or "inline", label="prompt-binding mode")
                else:
                    marker = f"ref_{uuid.uuid4().hex[:8]}"
                    mode = "inline"
                    b = {**b, "required": False}
            rows.append(
                {
                    "id": uuid.uuid4().hex,
                    "agent_id": agent_id,
                    "resource_id": b["resource_id"],
                    "marker": marker,
                    "mode": mode,
                    "slot": slot,
                    "attach_as_reference": 1 if b.get("attach_as_reference") else 0,
                    "pinned_version_id": b.get("pinned_version_id"),
                    "display_order": int(b.get("display_order", idx)),
                    "required": 1 if b.get("required", True) else 0,
                    "changelog": reason,
                    "created_at": now,
                    "created_by": actor,
                }
            )
        with self._engine.begin() as conn:
            conn.execute(
                agent_prompt_resource_bindings.delete().where(
                    agent_prompt_resource_bindings.c.agent_id == agent_id
                )
            )
            if rows:
                conn.execute(agent_prompt_resource_bindings.insert(), rows)
        return self.list_for_agent(agent_id)


# ---------------------------------------------------------------------------
# WorkspaceFileResourceBindingManager
# ---------------------------------------------------------------------------


class WorkspaceFileResourceBindingManager(Manager[WorkspaceFileResourceBinding]):
    """Manager for the ``workspace_file_resource_bindings`` table."""

    model = WorkspaceFileResourceBinding

    def list_for_workspace(self, workspace_id: str) -> list[WorkspaceFileBindingRow]:
        """Return all file bindings for a workspace ordered by display_order."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                workspace_file_resource_bindings.select()
                .where(workspace_file_resource_bindings.c.workspace_id == workspace_id)
                .order_by(workspace_file_resource_bindings.c.display_order)
            )
            return [cast(WorkspaceFileBindingRow, dict(r._mapping)) for r in rows]

    def count_by_workspace(self) -> dict[str, int]:
        """Return {workspace_id: binding_count} for all workspaces with bindings."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    workspace_file_resource_bindings.c.workspace_id,
                    func.count().label("n"),
                ).group_by(workspace_file_resource_bindings.c.workspace_id)
            )
            return {r._mapping["workspace_id"]: int(r._mapping["n"]) for r in rows}

    def replace_for_workspace(
        self,
        workspace_id: str,
        bindings: Iterable[dict],
        *,
        reason: str,
        actor: str | None = None,
    ) -> list[WorkspaceFileBindingRow]:
        """Atomically replace all file bindings for a workspace.

        Validates: no duplicate folder target_paths, valid materialize_mode,
        valid on_conflict, resource_id required.
        """
        reason = _validate_reason(reason)
        rows: list[dict] = []
        now = now_iso()
        seen_folder_targets: dict[str, str] = {}
        for idx, b in enumerate(bindings):
            mode = b.get("materialize_mode", "copy")
            MaterializeMode.coerce(mode, label="materialize_mode")
            on_conflict = b.get("on_conflict", "error")
            OnConflict.coerce(on_conflict, label="on_conflict")
            if not b.get("resource_id"):
                raise ValueError("resource_id is required for workspace bindings")
            target_path = b.get("target_path")
            if target_path and ".." in target_path.split("/"):
                raise ValueError(
                    f"target_path {target_path!r} must not contain '..' segments"
                )
            if target_path:
                # Check for folder collision — fetch resource type from resources table
                with self._engine.connect() as conn:
                    rrow = conn.execute(
                        resources_table.select().where(
                            resources_table.c.id == b["resource_id"]
                        )
                    ).first()
                rtype = (dict(rrow._mapping) if rrow else {}).get("type")
                if rtype == "folder":
                    normalized = target_path.strip("/")
                    prior = seen_folder_targets.get(normalized)
                    if prior is not None:
                        raise ValueError(
                            f"target_path {target_path!r} used by multiple folder "
                            f"bindings ({prior!r} and {b['resource_id']!r}); each "
                            f"folder target_path must be unique within a workspace"
                        )
                    seen_folder_targets[normalized] = b["resource_id"]
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
        with self._engine.begin() as conn:
            conn.execute(
                workspace_file_resource_bindings.delete().where(
                    workspace_file_resource_bindings.c.workspace_id == workspace_id
                )
            )
            if rows:
                conn.execute(workspace_file_resource_bindings.insert(), rows)
        return self.list_for_workspace(workspace_id)

    def replace_skill_bindings(
        self,
        workspace_id: str,
        skill_resource_ids: Iterable[str],
        *,
        reason: str = "skill bindings update",
        actor: str | None = None,
    ) -> list[WorkspaceFileBindingRow]:
        """Replace ONLY skill-type bindings, preserving other binding types."""
        current = self.list_for_workspace(workspace_id)
        merged: list[dict] = []
        order = 0
        for b in current:
            # Check if this binding is for a skill resource
            with self._engine.connect() as conn:
                rrow = conn.execute(
                    resources_table.select().where(
                        resources_table.c.id == b["resource_id"]
                    )
                ).first()
            rtype = (dict(rrow._mapping) if rrow else {}).get("type")
            if rtype == "skill":
                # Drop existing skill bindings — they will be replaced
                continue
            merged.append(
                {
                    "resource_id": b["resource_id"],
                    "target_path": b.get("target_path"),
                    "pinned_version_id": b.get("pinned_version_id"),
                    "materialize_mode": b.get("materialize_mode", "copy"),
                    "on_conflict": b.get("on_conflict", "error"),
                    "display_order": order,
                }
            )
            order += 1
        for rid in skill_resource_ids:
            merged.append(
                {
                    "resource_id": rid,
                    "target_path": None,
                    "materialize_mode": "copy",
                    "on_conflict": "skip",
                    "display_order": order,
                }
            )
            order += 1
        return self.replace_for_workspace(workspace_id, merged, reason=reason, actor=actor)
