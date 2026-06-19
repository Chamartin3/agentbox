"""Resource-bindings slice of the workspace-tool catalog.

Returns ``list[CallableItem]`` for the file resource bindings active in
a workspace.
"""

from __future__ import annotations

from typing import Any

from agentbox.core.tools.catalog import CallableItem


def resolve_resource_callables(
    workspace_id: str,
    store: Any,
) -> list[CallableItem]:
    """Return CallableItems for every file-resource binding in the workspace.

    *store* must have ``list_workspace_file_bindings(workspace_id)``
    (satisfied by ``SessionStore`` / ``RunStore`` at runtime).
    """
    bindings = store.list_workspace_file_bindings(workspace_id)
    return [
        CallableItem(
            name=b.get("target_path", b.get("resource_id", "")),
            kind="resource",
            description=f"Resource binding: {b.get('resource_id', '')}",
            policy={"resource_id": b.get("resource_id", ""), "target_path": b.get("target_path", "")},
        )
        for b in bindings
    ]
