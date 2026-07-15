"""WorkspaceRuntimePermission model and manager — runtime permission constraints per workspace.

Maps to the ``workspace_runtime_permissions`` table.
"""
from __future__ import annotations

from typing import Optional, cast

from sqlalchemy import JSON
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Field

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename
from agentbox.core.db.schema import workspace_runtime_permissions
from agentbox.core.data._util import now_iso
from agentbox.core.data.rows import PermissionFileEntry, WorkspaceRuntimePermissionRow


class WorkspaceRuntimePermission(Entity, table=True):
    """Runtime permission constraints applied to runs in a workspace."""

    __tablename__ = tablename("workspace_runtime_permissions")

    workspace_id: str = Field(primary_key=True)
    allowed_builtin_tools: Optional[list[str]] = Field(default=None, sa_type=JSON)
    files: Optional[list[dict]] = Field(default=None, sa_type=JSON)
    max_tokens: Optional[int] = Field(default=None)
    allow_file_write: Optional[int] = Field(default=None)
    allow_network: Optional[int] = Field(default=None)
    updated_at: str = Field(nullable=False)
    updated_by: Optional[str] = Field(default=None)


def _bool_to_int(b: bool | None) -> int | None:
    if b is None:
        return None
    return 1 if b else 0


class WorkspaceRuntimePermissionManager(Manager[WorkspaceRuntimePermission]):
    """Manager for the ``workspace_runtime_permissions`` table."""

    model = WorkspaceRuntimePermission

    # ── pure-DB primitives (ported from RuntimePermissionsMixin) ─────────

    def get_for_workspace(self, workspace_id: str) -> WorkspaceRuntimePermissionRow | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                workspace_runtime_permissions.select().where(
                    workspace_runtime_permissions.c.workspace_id == workspace_id
                )
            ).first()
        if row is None:
            return None
        return cast(WorkspaceRuntimePermissionRow, dict(row._mapping))

    def set_for_workspace(
        self,
        workspace_id: str,
        *,
        allowed_builtin_tools: list[str] | None = None,
        files: list[PermissionFileEntry] | None = None,
        max_tokens: int | None = None,
        allow_file_write: bool | None = None,
        allow_network: bool | None = None,
        actor: str | None = None,
    ) -> WorkspaceRuntimePermissionRow:
        existing = self.get_for_workspace(workspace_id) or cast(WorkspaceRuntimePermissionRow, {})
        values = {
            "workspace_id": workspace_id,
            "allowed_builtin_tools": (
                allowed_builtin_tools
                if allowed_builtin_tools is not None
                else existing.get("allowed_builtin_tools")
            ),
            "files": files if files is not None else existing.get("files"),
            "max_tokens": (
                max_tokens if max_tokens is not None else existing.get("max_tokens")
            ),
            "allow_file_write": (
                _bool_to_int(allow_file_write)
                if allow_file_write is not None
                else existing.get("allow_file_write")
            ),
            "allow_network": (
                _bool_to_int(allow_network)
                if allow_network is not None
                else existing.get("allow_network")
            ),
            "updated_at": now_iso(),
            "updated_by": actor,
        }
        stmt = sqlite_insert(workspace_runtime_permissions).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[workspace_runtime_permissions.c.workspace_id],
            set_={k: v for k, v in values.items() if k != "workspace_id"},
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        result = self.get_for_workspace(workspace_id)
        assert result is not None, f"workspace {workspace_id!r} runtime permission must exist after upsert"
        return result
