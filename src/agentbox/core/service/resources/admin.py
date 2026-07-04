"""Workspace file-binding admin free functions.

Thin pass-throughs to ``ResourceService`` for facade callers. Relocated from
the former top-level ``core.service.workspace_admin`` bridge so file-binding
helpers live in the resources domain that owns them.
"""

from __future__ import annotations

from agentbox.core.data.rows import WorkspaceFileBindingRow
from agentbox.core.service.resources.service import ResourceService


def list_workspace_file_bindings(workspace_id: str) -> list[WorkspaceFileBindingRow]:
    return ResourceService()._file_bindings.list_for_workspace(workspace_id)


def replace_workspace_file_bindings(
    workspace_id: str,
    bindings: list,
    *,
    reason: str,
    actor: str | None = None,
) -> list[WorkspaceFileBindingRow]:
    return ResourceService()._file_bindings.replace_for_workspace(
        workspace_id, bindings, reason=reason, actor=actor
    )
