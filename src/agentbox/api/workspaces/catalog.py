"""Workspace-scoped availability catalog.

``GET /api/workspaces/{workspace_id}/available_tools`` returns the
union of everything the workspace has *installed* — MCP-server tools,
host-environment capabilities, and resource bindings — expressed in
canonical vocabulary where applicable.

This is the pick-list the agent's authorization surface draws from;
it is **not** a global taxonomy reference (that remains
``/api/agent_tools``).

The actual resolution lives in domain catalog modules under
``core/workspaces/`` / ``core/resources/``; this endpoint is a thin
collector that gathers their slices and serialises the result.
"""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from fastapi import APIRouter, Depends

from agentbox.api.deps import get_mcp_registry, get_workspace_service
from agentbox.core.data import GrantParam, JsonSchemaDict
from agentbox.core.service.workspaces import WorkspaceService
from agentbox.core.tools.catalog import CallableItem
from agentbox.core.mcp.registry import McpRegistry

router = APIRouter(tags=["workspace-catalog"])


class AvailableToolsItem(TypedDict, total=False):
    """One available tool in the catalog.

    Structure varies by kind: mcp items include input_schema, host_env items
    include grant_schema, resource items include resource_id/target_path.
    """

    name: str
    description: str
    kind: str  # "mcp" | "host_env" | "resource"
    server: NotRequired[str | None]  # mcp only
    input_schema: NotRequired[JsonSchemaDict]  # mcp only; validated JSON Schema
    grant_schema: NotRequired[dict[str, GrantParam]]  # host_env only
    resource_id: NotRequired[str]  # resource only
    target_path: NotRequired[str]  # resource only


class AvailableToolsResponse(TypedDict):
    """Response from ``GET /api/workspaces/{workspace_id}/available_tools``."""

    items: list[AvailableToolsItem]


def _item_as_dict(item: CallableItem) -> AvailableToolsItem:
    """Convert a CallableItem to the wire shape expected by the API contract.

    The shape varies slightly by kind — the ``policy`` field (the
    internal name) is exposed as ``grant_schema`` for host_env items
    and flattened into the body for resource items, matching the
    pre-refactoring contract.
    """
    d: AvailableToolsItem = {
        "name": item.name,
        "description": item.description,
        "kind": item.kind,
    }
    if item.kind == "mcp":
        d["server"] = item.server
        if item.input_schema is not None:
            d["input_schema"] = item.input_schema
    elif item.kind == "host_env":
        if item.policy is not None:
            d["grant_schema"] = item.policy
    elif item.kind == "resource" and item.policy is not None:
        # `or ""` (not `.get(k, "")`): a binding row may carry the key with a
        # None value, which the default-arg form would pass straight through
        # and trip the `str` response contract → 500.
        d["resource_id"] = item.policy.get("resource_id") or ""
        d["target_path"] = item.policy.get("target_path") or ""
    return d


@router.get("/api/workspaces/{workspace_id}/available_tools")
def list_available_tools(
    workspace_id: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    mcp_registry: Annotated[McpRegistry, Depends(get_mcp_registry)],
) -> AvailableToolsResponse:
    """Return every tool, capability, and resource *installed* in this workspace.

    The agent's authorization pick-list is drawn from this catalog.
    ``/api/agent_tools`` remains the global taxonomy reference.
    """
    # Discovery may have run in a throwaway registry (a run, or /mcp/refresh)
    # after this singleton was built — reload the on-disk cache so freshly
    # discovered MCP tools show up without a server restart.
    mcp_registry.hydrate_from_cache()
    items = svc.installed_callables(workspace_id, mcp_registry=mcp_registry)
    return {"items": [_item_as_dict(i) for i in items]}
