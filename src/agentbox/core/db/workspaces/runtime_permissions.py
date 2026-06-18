"""Workspace runtime-permissions overlay.

Overlays per-workspace runtime permissions (built-in tool allow-list,
file scopes, token cap, file-write + network flags) over the
``WorkspaceDef`` defaults declared in ``agentbox.toml``. Same pattern as
``workspace_mcp_overrides``: TOML declares the baseline, the DB row is
the editable override layer, and unset columns mean "inherit".

``allowed_tools`` (MCP tool grants) is intentionally NOT stored here —
it derives from ``workspace_mcp_tool_overrides`` + policy at read time.
"""

from __future__ import annotations
import warnings

from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from agentbox.core.db.utils import now_iso
from agentbox.core.db.schema import workspace_runtime_permissions


class RuntimePermissionsMixin:
    engine: Engine

    def get_workspace_runtime_permissions(self, workspace_id: str) -> dict | None:
        """
    .. deprecated::
        Use ``db.workspace_runtime_permissions`` manager methods instead.

    Return the raw DB overlay row, or ``None`` if no row exists.

        The caller is responsible for merging with ``WorkspaceDef`` defaults.
        Returns columns with their stored types — ``allow_file_write`` /
        ``allow_network`` come back as ``int | None`` (SQLite has no bool).
        """
        warnings.warn(
            "RuntimePermissionsMixin.get_workspace_runtime_permissions is deprecated; use db.workspace_runtime_permissions manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                workspace_runtime_permissions.select().where(
                    workspace_runtime_permissions.c.workspace_id == workspace_id
                )
            ).first()
        if row is None:
            return None
        return dict(row._mapping)

    def set_workspace_runtime_permissions(
        self,
        workspace_id: str,
        *,
        allowed_builtin_tools: list[str] | None = None,
        files: list[dict] | None = None,
        max_tokens: int | None = None,
        allow_file_write: bool | None = None,
        allow_network: bool | None = None,
        actor: str | None = None,
    ) -> dict:
        """Upsert the overlay row. ``None`` for a field clears that override
        (back to manifest default). Any field omitted from the kwargs keeps
        its existing stored value (partial update)."""
        warnings.warn(
            "RuntimePermissionsMixin.set_workspace_runtime_permissions is deprecated; use db.workspace_runtime_permissions manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        existing = self.get_workspace_runtime_permissions(workspace_id) or {}
        values: dict[str, Any] = {
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
        with self.engine.begin() as conn:
            conn.execute(stmt)
        return self.get_workspace_runtime_permissions(workspace_id) or {}


def _bool_to_int(b: bool | None) -> int | None:
    if b is None:
        return None
    return 1 if b else 0
