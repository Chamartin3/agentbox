"""/mcp endpoints — introspection of connected MCP servers and their tools."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agentbox.api.deps import get_mcp_registry

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/servers")
def list_mcp_servers() -> dict:
    """Return all configured MCP servers with their health and tool counts."""
    registry = get_mcp_registry()
    report = registry.health_report()
    servers: list[dict] = []
    for name, health in report.servers.items():
        entry = health.to_dict()
        entry["name"] = name
        servers.append(entry)
    return {
        "servers": servers,
        "overall_status": report.overall,
    }


@router.get("/servers/{name}/tools")
def get_server_tools(name: str) -> dict:
    """Return tools for a specific MCP server."""
    registry = get_mcp_registry()
    tools = registry.manifest.server_tools(name)
    health = registry.server_health(name)
    if not tools and (health is None or health.status == "unavailable"):
        raise HTTPException(404, f"MCP server {name!r} not found or unavailable")
    return {
        "server": name,
        "status": health.to_dict() if health else {"status": "unknown"},
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
def get_server_groups(name: str) -> dict:
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
