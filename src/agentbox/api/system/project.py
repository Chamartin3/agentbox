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
import json
import time
from pathlib import Path
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.config import load_settings
from agentbox.core.service import McpServerSpec
from agentbox.core.workspaces.tooling.mcp.transport import McpClient, McpError

router = APIRouter(prefix="/api/project", tags=["project"])

_INTROSPECT_TIMEOUT = 30.0  # seconds — bounds a hung/slow MCP server


# Persisted introspection cache: the Settings table shows tool/resource counts
# for every server on load, so we can't re-spawn each server on every page
# visit. Results are cached to disk; the modal's "refresh" forces a live re-read.
def _introspect_cache_path(name: str) -> Path:
    d = load_settings().mcp_cache_dir / "introspect"
    d.mkdir(parents=True, exist_ok=True)
    # server names are user-supplied — keep only filename-safe chars.
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return d / f"{safe}.json"


def _read_introspect_cache(name: str) -> IntrospectResult | None:
    path = _introspect_cache_path(name)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "server": name,
        "tools": data.get("tools", []),
        "resources": data.get("resources", []),
        "error": None,
    }


def _write_introspect_cache(result: IntrospectResult) -> None:
    try:
        _introspect_cache_path(result["server"]).write_text(
            json.dumps(
                {
                    "tools": result["tools"],
                    "resources": result["resources"],
                    "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


class McpServerSpecDumped(TypedDict):
    """McpServerSpec as returned by model_dump(mode="json"), plus cached counts."""

    name: str
    url: str | None
    transport: str
    command: list[str] | None
    cache_ttl: int
    # From the persisted introspection cache; None when never introspected.
    tool_count: int | None
    resource_count: int | None
    # Set by the probe on upsert: the reason the server could not be run, or
    # None when it responded (or was never probed on this response).
    error: str | None


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
        cached = _read_introspect_cache(dumped["name"])
        entry: McpServerSpecDumped = {
            "name": dumped["name"],
            "url": dumped["url"],
            "transport": dumped["transport"],
            "command": dumped["command"],
            "cache_ttl": dumped["cache_ttl"],
            "tool_count": len(cached["tools"]) if cached else None,
            "resource_count": len(cached["resources"]) if cached else None,
            "error": None,
        }
        result.append(entry)
    return {"servers": result}


@router.put("/mcp-servers/{name}")
async def upsert_project_mcp_server(
    name: str,
    spec: McpServerSpec,
    force: bool = False,
    ctx: APIContext = Depends(get_api_context),
) -> McpServerSpecDumped:
    if spec.name != name:
        spec = spec.model_copy(update={"name": name})
    # Probe BEFORE persisting so a broken or uninstalled server never enters
    # the list. For uvx/npx specs the probe also triggers the package install,
    # so a green probe means "installed and runnable".
    try:
        probe = await asyncio.wait_for(_introspect(spec), timeout=_INTROSPECT_TIMEOUT)
    except TimeoutError:
        probe = {
            "server": name,
            "tools": [],
            "resources": [],
            "error": f"timed out after {_INTROSPECT_TIMEOUT:.0f}s",
        }
    if probe["error"] and not force:
        # ponytail: gate on probe; force=true is the escape hatch for editing a
        # server whose backend is momentarily down. No "save anyway" UI button
        # until someone actually needs one.
        raise HTTPException(
            status_code=422,
            detail=f"{name} failed to run: {probe['error']} "
            f"— fix the command or retry with ?force=true to save anyway",
        )
    ctx.system.set_project_mcp_server(spec)
    dumped = spec.model_dump(mode="json")
    result: McpServerSpecDumped = {
        "name": dumped["name"],
        "url": dumped["url"],
        "transport": dumped["transport"],
        "command": dumped["command"],
        "cache_ttl": dumped["cache_ttl"],
        "tool_count": len(probe["tools"]),
        "resource_count": len(probe["resources"]),
        "error": probe["error"],
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
    except (McpError, OSError) as exc:
        # McpError = protocol/transport failure; OSError = command not found /
        # spawn failure. Either way, report it in the modal, never 500.
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
    result: IntrospectResult = {
        "server": spec.name,
        "tools": tools,
        "resources": resources,
        "error": None,
    }
    _write_introspect_cache(result)  # persist so table counts survive refresh
    return result


@router.post("/mcp-servers/{name}/introspect")
async def introspect_project_mcp_server(
    name: str,
    refresh: bool = False,
    ctx: APIContext = Depends(get_api_context),
) -> IntrospectResult:
    """List a global MCP server's tools + resources. Served from the persisted
    cache when present; ``refresh=true`` forces a live re-read."""
    spec = next((s for s in ctx.system.get_project_mcp_servers() if s.name == name), None)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown mcp server: {name!r}")
    if not refresh:
        cached = _read_introspect_cache(name)
        if cached is not None:
            return cached
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
