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

from agentbox.core.data._protocol import StoreContext
from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import (
    agent_prompt_resource_bindings,
    workspace_file_resource_bindings,
    workspace_subagents,
)

VALID_PROMPT_MODES = ("inline", "skill_primer", "name_only", "manifest")
VALID_PROMPT_SLOTS = ("system", "user_template", "input_schema", "output_schema")
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
                if slot not in VALID_PROMPT_SLOTS:
                    raise ValueError(
                        f"Invalid prompt-binding slot {slot!r}; must be one of {VALID_PROMPT_SLOTS}"
                    )
                if slot in slots_seen:
                    raise ValueError(
                        f"Duplicate prompt-binding slot {slot!r} for agent {agent_id!r}"
                    )
                slots_seen.add(slot)
                # Schemas don't need a marker or mode; ignore them if posted.
                marker = marker or None
                mode = mode or None
            else:
                # marker/mode are optional: when caller doesn't provide them,
                # this is a reference-only binding (appended to ## References
                # under the resource's display_name, not spliced into the
                # template). A synthetic non-splicing marker is stored to
                # satisfy the legacy NOT-NULL check constraint.
                if marker:
                    if mode not in VALID_PROMPT_MODES:
                        raise ValueError(
                            f"Invalid prompt-binding mode {mode!r}; must be one of {VALID_PROMPT_MODES}"
                        )
                else:
                    marker = f"ref_{uuid.uuid4().hex[:8]}"
                    mode = "inline"
                    # Reference-only bindings should never warn about
                    # an unreferenced marker — they are not spliced.
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
        self: StoreContext,
        workspace_id: str,
        bindings: Iterable[dict],
        *,
        reason: str,
        actor: str | None = None,
    ) -> list[dict]:
        reason = _validate_reason(reason)
        rows = []
        now = now_iso()
        # Collect folder-type target paths separately from single-file paths.
        # Single-file bindings with the same ``target_path`` no longer
        # collide because each resolves to a different filename inside it
        # (see ``_resolve_target_path`` in workspace_materialize.py).
        # Folder-type bindings DO collide on the same path.
        seen_folder_targets: dict[str, str] = {}
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
            # Folder collisions: two folder-type bindings cannot share a
            # target_path. Look up the resource type to know which kind
            # of binding this is.
            if target_path:
                resource = self.get_repo_resource(b["resource_id"])
                rtype = (resource or {}).get("type")
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
        with self.engine.begin() as conn:
            conn.execute(
                workspace_file_resource_bindings.delete().where(
                    workspace_file_resource_bindings.c.workspace_id == workspace_id
                )
            )
            if rows:
                conn.execute(workspace_file_resource_bindings.insert(), rows)
        return self.list_workspace_file_bindings(workspace_id)

    def replace_workspace_skill_bindings(
        self: StoreContext,
        workspace_id: str,
        skill_resource_ids: Iterable[str],
        *,
        reason: str = "skill bindings update",
        actor: str | None = None,
    ) -> list[dict]:
        """Replace ONLY the skill-type bindings for a workspace.

        Bindings of other types (document, folder, schema, script) are
        preserved exactly as-is. Skill bindings use defaults: null
        ``target_path`` (skill name resolves via ``_default_target_path``
        → ``.claude/skills/<name>``), ``materialize_mode=copy``,
        ``on_conflict=skip``.
        """
        current = self.list_workspace_file_bindings(workspace_id)
        merged: list[dict] = []
        order = 0
        for b in current:
            resource = self.get_repo_resource(b["resource_id"])
            if resource and resource.get("type") == "skill":
                # Drop existing skill bindings — they will be replaced.
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
        return self.replace_workspace_file_bindings(
            workspace_id, merged, reason=reason, actor=actor
        )

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
