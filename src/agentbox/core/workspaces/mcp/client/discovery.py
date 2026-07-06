"""MCP tool discovery — spawn servers and retrieve their tool lists.

Supports both stdio (subprocess) and HTTP/SSE MCP servers.  Failures are
non-fatal: a warning is logged and an empty list is returned for the
problematic server.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

import httpx

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

_INITIALIZE = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "agentbox-discovery", "version": "0.1"},
        },
    }
)

_TOOLS_LIST = json.dumps(
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
)


def _extract_tool_names(raw: str) -> list[str]:
    """Parse a JSON-RPC response and return ``result.tools[].name``."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return []
    result = obj.get("result")
    if not isinstance(result, dict):
        return []
    tools = result.get("tools") or []
    names: list[str] = []
    for t in tools:
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            names.append(t["name"])
    return names


# ---------------------------------------------------------------------------
# Per-server discovery implementations
# ---------------------------------------------------------------------------


async def _discover_stdio(
    name: str, command: str, args: list[str], timeout: float
) -> list[str]:
    """Spawn a stdio MCP server and ask for tools/list."""
    cmd = [command, *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        payload = (_INITIALIZE + "\n" + _TOOLS_LIST + "\n").encode()
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=payload), timeout=timeout
        )
    except TimeoutError:
        _log.warning(
            "mcp-discovery: stdio server %r timed out after %ss", name, timeout
        )
        with contextlib.suppress(Exception):
            proc.kill()
        return []
    finally:
        with contextlib.suppress(Exception):
            proc.kill()

    # Parse line by line — the tools/list response is the *second* JSON line
    tools: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        names = _extract_tool_names(line.decode(errors="replace"))
        if names:
            tools.extend(names)
    return tools


async def _discover_http(name: str, url: str, timeout: float) -> list[str]:
    """POST ``url/tools/list`` and parse the JSON-RPC response."""
    endpoint = url.rstrip("/") + "/tools/list"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return _extract_tool_names(resp.text)
    except Exception as exc:
        _log.warning("mcp-discovery: HTTP server %r failed: %s", name, exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _discover_one(server: dict, timeout: float) -> tuple[str, list[str]]:
    name: str = server.get("name", "<unknown>")
    try:
        if "url" in server:
            tools = await _discover_http(name, server["url"], timeout)
        elif "command" in server:
            args: list[str] = server.get("args", [])
            tools = await _discover_stdio(name, server["command"], args, timeout)
        else:
            _log.warning(
                "mcp-discovery: server %r has neither 'url' nor 'command' — skipping",
                name,
            )
            tools = []
    except Exception as exc:
        _log.warning("mcp-discovery: server %r raised unexpected error: %s", name, exc)
        tools = []
    return name, tools


async def discover_tools(
    servers: list[dict], *, timeout: float = 10.0
) -> dict[str, list[str]]:
    """Discover tools from a list of MCP server descriptors.

    Each *server* dict must contain at minimum:
    - ``name`` — a human-readable identifier.
    - Either ``url`` (HTTP/SSE server) **or** ``command`` + optional ``args``
      (stdio server).

    Returns ``{server_name: [tool_name, ...]}``; failures produce an empty
    list for the affected server and are logged at WARNING level.
    """
    if not servers:
        return {}

    tasks = [_discover_one(s, timeout) for s in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: dict[str, list[str]] = {}
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            name = servers[i].get("name", f"server-{i}")
            _log.warning("mcp-discovery: gather error for %r: %s", name, result)
            out[name] = []
        else:
            name, tools = result
            out[name] = tools
    return out
