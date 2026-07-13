"""MCP state — server health shapes and the ``McpRegistry`` (inventory +
cached manifests + health).

Merges the former client/health.py + client/registry.py.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

from agentbox.core.data import McpHealthReportDict, McpServerHealthDict
from agentbox.core.workspaces.tooling.mcp.manifest import McpToolManifest, Tool
from agentbox.core.workspaces.tooling.mcp.transport import McpClient

ServerStatus = Literal["ok", "degraded", "unavailable"]


class ServerHealth:
    __slots__ = ("fetched_at", "last_error", "status", "tool_count")

    def __init__(
        self,
        status: ServerStatus = "unavailable",
        tool_count: int = 0,
        fetched_at: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self.status = status
        self.tool_count = tool_count
        self.fetched_at = fetched_at
        self.last_error = last_error

    def to_dict(self) -> McpServerHealthDict:
        d: McpServerHealthDict = {
            "status": self.status,
            "tool_count": self.tool_count,
        }
        if self.fetched_at is not None:
            d["fetched_at"] = self.fetched_at
        if self.last_error is not None:
            d["last_error"] = self.last_error
        return d


class McpHealthReport:
    __slots__ = ("overall", "servers")

    def __init__(self, overall: ServerStatus, servers: dict[str, ServerHealth]) -> None:
        self.overall = overall
        self.servers = servers

    def to_dict(self) -> McpHealthReportDict:
        return {
            "status": self.overall,
            "mcp_servers": {name: h.to_dict() for name, h in self.servers.items()},
        }


class CachedTool(TypedDict):
    """On-disk tool cache entry (snake_case field names)."""

    name: str
    description: str
    input_schema: dict[str, Any] | None


class McpServerConfig(TypedDict, total=False):
    """Spec for one MCP server entry as passed to ``sync_servers``."""

    name: str
    url: str
    transport: str
    command: list[str]
    cache_ttl: int


_CACHE_TTL = 300


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class McpRegistry:
    """Central registry for MCP server state.

    On startup, iterates ``[[mcp_servers]]`` entries, attempts to connect
    and list tools, and populates the manifest. Failures fall back to
    disk cache and mark the server as degraded/unavailable.
    """

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = McpToolManifest()
        self._health: dict[str, ServerHealth] = {}
        self._clients: dict[str, McpClient] = {}

    @property
    def manifest(self) -> McpToolManifest:
        return self._manifest

    def server_health(self, name: str) -> ServerHealth | None:
        return self._health.get(name)

    def reset_health(self) -> None:
        self._health.clear()

    def health_report(self) -> McpHealthReport:
        overall = self._compute_overall_status()
        return McpHealthReport(overall=overall, servers=dict(self._health))

    def _compute_overall_status(self) -> ServerStatus:
        if not self._health:
            return "unavailable"
        statuses = {h.status for h in self._health.values()}
        if statuses == {"ok"}:
            return "ok"
        if any(h.status == "ok" for h in self._health.values()):
            return "degraded"
        if any(h.status == "degraded" for h in self._health.values()):
            return "degraded"
        return "unavailable"

    async def sync_servers(self, servers: list[McpServerConfig]) -> None:
        all_tools: dict[str, list[Tool]] = {}
        for spec in servers:
            name = spec.get("name", "mcp")
            url = spec.get("url")
            transport = spec.get("transport", "http")
            command = spec.get("command")
            ttl = spec.get("cache_ttl", _CACHE_TTL)

            health = await self._sync_one(name, url, transport, command, ttl)
            self._health[name] = health
            if health.status in ("ok", "degraded"):
                cached = self._load_cache(name)
                if cached:
                    tools = [Tool(**t) if isinstance(t, dict) else t for t in cached]
                    all_tools[name] = tools

        self._manifest.set_servers(all_tools)

    async def _sync_one(
        self,
        name: str,
        url: str | None,
        transport: str,
        command: list[str] | None,
        ttl: int,
    ) -> ServerHealth:
        client = McpClient(name, url=url, transport=transport, command=command)
        self._clients[name] = client
        try:
            tools_data = await client.list_tools()
            tools = [
                Tool(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema"),
                )
                for t in tools_data
            ]
            cache_entries: list[CachedTool] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
            self._save_cache(name, cache_entries)
            return ServerHealth(
                status="ok",
                tool_count=len(tools),
                fetched_at=_now_iso(),
            )
        except Exception as exc:
            cached = self._load_cache(name)
            if cached is not None:
                return ServerHealth(
                    status="degraded",
                    tool_count=len(cached),
                    fetched_at=_now_iso(),
                    last_error=str(exc),
                )
            return ServerHealth(
                status="unavailable",
                last_error=str(exc),
            )

    def _cache_path(self, server_name: str) -> Path:
        return self.cache_dir / f"{server_name}.json"

    def _save_cache(self, server_name: str, tools: list[CachedTool]) -> None:
        try:
            path = self._cache_path(server_name)
            path.write_text(
                json.dumps({"tools": tools, "cached_at": _now_iso()}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _load_cache(self, server_name: str) -> list[CachedTool] | None:
        path = self._cache_path(server_name)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("tools", [])
        except (json.JSONDecodeError, OSError):
            return None
