"""/mcp endpoints — introspection of connected MCP servers and their tools."""

from __future__ import annotations

from typing import TypedDict, NotRequired

from fastapi import APIRouter, HTTPException

from agentbox.api.deps import get_mcp_registry
from agentbox.core.data import JsonSchemaDict

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class ServerHealthEntry(TypedDict):
    """Server health status with optional fields."""

    status: str
    tool_count: NotRequired[int]
    fetched_at: NotRequired[str]
    last_error: NotRequired[str]


class McpServerEntry(TypedDict):
    """One entry in the servers list."""

    name: str
    status: str
    tool_count: NotRequired[int]
    fetched_at: NotRequired[str]
    last_error: NotRequired[str]


class ListMcpServersResult(TypedDict):
    """Response envelope for GET /api/mcp/servers."""

    servers: list[McpServerEntry]
    overall_status: str


class ToolEntry(TypedDict):
    """One tool entry."""

    name: str
    description: str
    input_schema: JsonSchemaDict | None


class GetServerToolsResult(TypedDict):
    """Response envelope for GET /api/mcp/servers/{name}/tools."""

    server: str
    status: ServerHealthEntry
    tools: list[ToolEntry]
    tool_count: int


class ToolGroupEntry(TypedDict):
    """One tool group entry."""

    name: str
    tools: list[str]
    tool_count: int


class GetServerGroupsResult(TypedDict):
    """Response envelope for GET /api/mcp/servers/{name}/groups."""

    server: str
    groups: list[ToolGroupEntry]
    group_count: int


@router.get("/servers")
def list_mcp_servers() -> ListMcpServersResult:
    """Return all configured MCP servers with their health and tool counts."""
    registry = get_mcp_registry()
    report = registry.health_report()
    servers: list[McpServerEntry] = []
    for name, health in report.servers.items():
        health_dict = health.to_dict()
        entry: McpServerEntry = {
            "name": name,
            "status": health_dict["status"],
        }
        if "tool_count" in health_dict:
            entry["tool_count"] = health_dict["tool_count"]
        if "fetched_at" in health_dict:
            entry["fetched_at"] = health_dict["fetched_at"]
        if "last_error" in health_dict:
            entry["last_error"] = health_dict["last_error"]
        servers.append(entry)
    return {
        "servers": servers,
        "overall_status": report.overall,
    }


@router.get("/servers/{name}/tools")
def get_server_tools(name: str) -> GetServerToolsResult:
    """Return tools for a specific MCP server."""
    registry = get_mcp_registry()
    tools = registry.manifest.server_tools(name)
    health = registry.server_health(name)
    if not tools and (health is None or health.status == "unavailable"):
        raise HTTPException(404, f"MCP server {name!r} not found or unavailable")

    if health:
        health_dict = health.to_dict()
        status: ServerHealthEntry = {"status": health_dict["status"]}
        if "tool_count" in health_dict:
            status["tool_count"] = health_dict["tool_count"]
        if "fetched_at" in health_dict:
            status["fetched_at"] = health_dict["fetched_at"]
        if "last_error" in health_dict:
            status["last_error"] = health_dict["last_error"]
    else:
        status = {"status": "unknown"}

    return {
        "server": name,
        "status": status,
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ],
        "tool_count": len(tools),
    }


@router.get("/servers/{name}/groups")
def get_server_groups(name: str) -> GetServerGroupsResult:
    """Return derived tool groups for a specific MCP server."""
    registry = get_mcp_registry()
    health = registry.server_health(name)
    if health is None or health.status == "unavailable":
        raise HTTPException(404, f"MCP server {name!r} not found or unavailable")
    groups = {
        k: v for k, v in registry.manifest.groups.items() if k.startswith(f"{name}.")
    }
    return {
        "server": name,
        "groups": [
            {"name": k, "tools": v, "tool_count": len(v)}
            for k, v in sorted(groups.items())
        ],
        "group_count": len(groups),
    }
