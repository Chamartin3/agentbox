"""/api/project — typed wrappers over the DB-backed project config.

Project-level settings (formerly in ``agentbox.toml``) live in the
``settings`` table. ``/api/settings/{section}`` exposes the raw
key/value section; this module adds typed CRUD for the structured
``project_mcp_servers`` section so the UI can manage individual
servers without hand-rolling JSON.

For ``project_shared_assets`` and ``project_runtime`` (flat scalars),
continue using ``PATCH /api/settings/{section}``.
"""

from __future__ import annotations

import asyncio
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.service import McpServerSpec
from agentbox.core.workspaces.tooling.mcp.transport import McpClient, McpError

router = APIRouter(prefix="/api/project", tags=["project"])

# ponytail: live connect-and-read on demand, no persisted cache. The modal
# re-fetches on "refresh"; add a DB cache only if always-on table counts matter.
_INTROSPECT_TIMEOUT = 30.0  # seconds — bounds a hung/slow MCP server


class McpServerSpecDumped(TypedDict):
    """McpServerSpec as returned by model_dump(mode="json")."""

    name: str
    url: str | None
    transport: str
    command: list[str] | None
    cache_ttl: int


class ListProjectMcpServersResult(TypedDict):
    """Response envelope for GET /api/project/mcp-servers."""

    servers: list[McpServerSpecDumped]


class DeleteProjectMcpServerResult(TypedDict):
    """Response envelope for DELETE /api/project/mcp-servers/{name}."""

    deleted: str


@router.get("/mcp-servers")
def list_project_mcp_servers(ctx: APIContext = Depends(get_api_context)) -> ListProjectMcpServersResult:
    servers = ctx.system.get_project_mcp_servers()
    result: list[McpServerSpecDumped] = []
    for s in servers:
        dumped = s.model_dump(mode="json")
        entry: McpServerSpecDumped = {
            "name": dumped["name"],
            "url": dumped["url"],
            "transport": dumped["transport"],
            "command": dumped["command"],
            "cache_ttl": dumped["cache_ttl"],
        }
        result.append(entry)
    return {"servers": result}


@router.put("/mcp-servers/{name}")
def upsert_project_mcp_server(
    name: str,
    spec: McpServerSpec,
    ctx: APIContext = Depends(get_api_context),
) -> McpServerSpecDumped:
    if spec.name != name:
        spec = spec.model_copy(update={"name": name})
    ctx.system.set_project_mcp_server(spec)
    dumped = spec.model_dump(mode="json")
    result: McpServerSpecDumped = {
        "name": dumped["name"],
        "url": dumped["url"],
        "transport": dumped["transport"],
        "command": dumped["command"],
        "cache_ttl": dumped["cache_ttl"],
    }
    return result


class McpToolInfo(TypedDict):
    name: str
    description: str


class McpResourceInfo(TypedDict):
    uri: str
    name: str
    description: str


class IntrospectResult(TypedDict):
    """Live tools + resources discovered from a global MCP server."""

    server: str
    tools: list[McpToolInfo]
    resources: list[McpResourceInfo]
    error: str | None


async def _introspect(spec: McpServerSpec) -> IntrospectResult:
    # command servers use stdio regardless of the (url-only) transport field.
    transport = "stdio" if spec.command else spec.transport
    client = McpClient(
        spec.name, url=spec.url, transport=transport, command=spec.command
    )
    try:
        raw_tools = await client.list_tools()
        raw_resources = await client.list_resources()
    except McpError as exc:
        return {"server": spec.name, "tools": [], "resources": [], "error": str(exc)}
    finally:
        await client.close()
    tools: list[McpToolInfo] = [
        {"name": t.get("name", ""), "description": t.get("description", "")}
        for t in raw_tools
    ]
    resources: list[McpResourceInfo] = [
        {
            "uri": r.get("uri", ""),
            "name": r.get("name", ""),
            "description": r.get("description", ""),
        }
        for r in raw_resources
    ]
    return {"server": spec.name, "tools": tools, "resources": resources, "error": None}


@router.post("/mcp-servers/{name}/introspect")
async def introspect_project_mcp_server(
    name: str,
    ctx: APIContext = Depends(get_api_context),
) -> IntrospectResult:
    """Connect to a global MCP server and list its tools + resources live."""
    spec = next((s for s in ctx.system.get_project_mcp_servers() if s.name == name), None)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown mcp server: {name!r}")
    try:
        return await asyncio.wait_for(_introspect(spec), timeout=_INTROSPECT_TIMEOUT)
    except TimeoutError:
        return {
            "server": name,
            "tools": [],
            "resources": [],
            "error": f"timed out after {_INTROSPECT_TIMEOUT:.0f}s",
        }


@router.delete("/mcp-servers/{name}")
def delete_project_mcp_server(
    name: str,
    ctx: APIContext = Depends(get_api_context),
) -> DeleteProjectMcpServerResult:
    existing = {s.name for s in ctx.system.get_project_mcp_servers()}
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"unknown mcp server: {name!r}")
    ctx.system.delete_project_mcp_server(name)
    return {"deleted": name}
