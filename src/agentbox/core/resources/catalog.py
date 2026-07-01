"""Resource-bindings slice of the workspace-tool catalog.

Returns ``list[CallableItem]`` for the file resource bindings active in
a workspace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.tools.catalog import CallableItem

if TYPE_CHECKING:
    from agentbox.core.db import WorkspaceFileResourceBindingManager


def resolve_resource_callables(
    workspace_id: str,
    file_bindings: WorkspaceFileResourceBindingManager,
) -> list[CallableItem]:
    """Return CallableItems for every file-resource binding in the workspace."""
    bindings = file_bindings.list_for_workspace(workspace_id)
    return [
        CallableItem(
            name=b.get("target_path", b.get("resource_id", "")),
            kind="resource",
            description=f"Resource binding: {b.get('resource_id', '')}",
            policy={"resource_id": b.get("resource_id", ""), "target_path": b.get("target_path", "")},
        )
        for b in bindings
    ]
