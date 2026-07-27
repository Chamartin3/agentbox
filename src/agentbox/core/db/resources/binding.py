"""Resource binding models + managers — agent-prompt and workspace-file bindings.

Maps to the ``agent_prompt_resource_bindings`` and
``workspace_file_resource_bindings`` tables.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Optional, cast

from sqlalchemy import CheckConstraint, func, select, text
from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.data.constants import MaterializeMode, OnConflict, PromptMode, PromptSlot
from agentbox.core.data.payload_types import PromptBindingSpec, WorkspaceBindingSpec
from agentbox.core.data.rows import AgentPromptBindingRow, WorkspaceFileBindingRow
from agentbox.core.data._util import now_iso
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs
from agentbox.core.db.resources.resource import Resource


class AgentPromptResourceBinding(Entity, table=True):
    """Links a resource to a slot or marker in an agent's prompt composition."""

    __tablename__ = tablename("agent_prompt_resource_bindings")

    id: str = Field(primary_key=True)
    agent_id: str = Field(nullable=False)
    resource_id: str = Field(foreign_key="resources.id", nullable=False)
    marker: Optional[str] = Field(default=None)
    mode: Optional[str] = Field(default=None)
    slot: Optional[str] = Field(default=None)
    attach_as_reference: int = Field(nullable=False, default=0, sa_column_kwargs={"server_default": "0"})
    pinned_version_id: Optional[str] = Field(foreign_key="resource_versions.id", default=None)
    display_order: int = Field(nullable=False, default=0, sa_column_kwargs={"server_default": "0"})
    required: int = Field(nullable=False, default=1, sa_column_kwargs={"server_default": "1"})
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(
        CheckConstraint("mode IS NULL OR mode IN ('inline', 'skill_primer', 'name_only', 'manifest')", name="agent_prompt_bindings_mode_check"),
        CheckConstraint("slot IS NULL OR slot IN ('system', 'user_template', 'input_schema', 'output_schema')", name="agent_prompt_bindings_slot_check"),
        CheckConstraint("(slot IS NOT NULL) OR (marker IS NOT NULL AND mode IS NOT NULL)", name="agent_prompt_bindings_slot_or_marker"),
        CheckConstraint("required IN (0, 1)", name="agent_prompt_bindings_required_bool"),
        CheckConstraint("attach_as_reference IN (0, 1)", name="agent_prompt_bindings_reference_bool"),
        UniqueConstraint("agent_id", "marker", "resource_id", name="uq_agent_prompt_bindings_triple"),
        Index("ix_agent_prompt_bindings_agent", "agent_id"),
        Index("uq_agent_prompt_bindings_slot", "agent_id", "slot", unique=True, sqlite_where=text("slot IS NOT NULL")),
    )


class WorkspaceFileResourceBinding(Entity, table=True):
    """Links a resource to a target file path in a workspace."""

    __tablename__ = tablename("workspace_file_resource_bindings")

    id: str = Field(primary_key=True)
    workspace_id: str = Field(nullable=False)
    resource_id: str = Field(foreign_key="resources.id", nullable=False)
    target_path: Optional[str] = Field(default=None)
    pinned_version_id: Optional[str] = Field(foreign_key="resource_versions.id", default=None)
    materialize_mode: str = Field(nullable=False, default="copy", sa_column_kwargs={"server_default": "copy"})
    on_conflict: str = Field(nullable=False, default="error", sa_column_kwargs={"server_default": "error"})
    display_order: int = Field(nullable=False, default=0, sa_column_kwargs={"server_default": "0"})
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(
        CheckConstraint("materialize_mode IN ('copy', 'symlink', 'mount')", name="workspace_file_bindings_mode_check"),
        CheckConstraint("on_conflict IN ('error', 'overwrite', 'skip')", name="workspace_file_bindings_on_conflict_check"),
        UniqueConstraint("workspace_id", "resource_id", "target_path", name="uq_workspace_file_bindings_triple"),
        Index("ix_workspace_file_bindings_workspace", "workspace_id"),
    )


agent_prompt_resource_bindings = AgentPromptResourceBinding.__table__
workspace_file_resource_bindings = WorkspaceFileResourceBinding.__table__
resources_table = Resource.__table__


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

    def get_slot_binding(
        self, agent_id: str, slot: str
    ) -> AgentPromptBindingRow | None:
        """Return the binding for the given slot, or None if absent."""
        with self._engine.connect() as conn:
            row = conn.execute(
                agent_prompt_resource_bindings.select()
                .where(
                    agent_prompt_resource_bindings.c.agent_id == agent_id,
                    agent_prompt_resource_bindings.c.slot == slot,
                )
            ).first()
            return cast(AgentPromptBindingRow, dict(row._mapping)) if row else None

    def upsert_slot_binding(
        self,
        agent_id: str,
        slot: str,
        resource_id: str,
        version_id: str,
        *,
        reason: str,
        actor: str | None = None,
    ) -> AgentPromptBindingRow:
        """Insert or replace the binding for a specific slot.

        Unlike ``replace_for_agent``, this method only touches the one slot
        row; all other bindings for the agent are preserved.  The slot must
        be a valid :class:`~agentbox.core.data.constants.PromptSlot` value.

        ``version_id`` is always stored as ``pinned_version_id`` so the
        runtime resolver can find the blob without an extra version-pointer
        lookup.
        """
        PromptSlot.coerce(slot, label="prompt-binding slot")
        reason = _validate_reason(reason)
        now = now_iso()
        with self._engine.begin() as conn:
            # Delete any existing binding for this slot on this agent.
            conn.execute(
                agent_prompt_resource_bindings.delete().where(
                    agent_prompt_resource_bindings.c.agent_id == agent_id,
                    agent_prompt_resource_bindings.c.slot == slot,
                )
            )
            row_id = uuid.uuid4().hex
            conn.execute(
                agent_prompt_resource_bindings.insert().values(
                    id=row_id,
                    agent_id=agent_id,
                    resource_id=resource_id,
                    marker=None,
                    mode=None,
                    slot=slot,
                    attach_as_reference=0,
                    pinned_version_id=version_id,
                    display_order=0,
                    required=1,
                    changelog=reason,
                    created_at=now,
                    created_by=actor,
                )
            )
        binding = self.get_slot_binding(agent_id, slot)
        assert binding is not None, f"just-upserted slot binding {slot!r} must be retrievable"
        return binding

    def replace_for_agent(
        self,
        agent_id: str,
        bindings: Iterable[PromptBindingSpec],
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

    def count_skills_by_workspace(self) -> dict[str, int]:
        """Return {workspace_id: skill_binding_count} — only skill-type bindings.

        The workspaces table shows *associated* skills (bound skill
        resources), not on-disk SKILL.md discovery.
        """
        b = workspace_file_resource_bindings
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(b.c.workspace_id, func.count().label("n"))
                .select_from(b.join(resources_table, resources_table.c.id == b.c.resource_id))
                .where(resources_table.c.type == "skill")
                .group_by(b.c.workspace_id)
            )
            return {r._mapping["workspace_id"]: int(r._mapping["n"]) for r in rows}

    def replace_for_workspace(
        self,
        workspace_id: str,
        bindings: Iterable[WorkspaceBindingSpec],
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
        merged: list[WorkspaceBindingSpec] = []
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
