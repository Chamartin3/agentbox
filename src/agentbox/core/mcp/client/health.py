from __future__ import annotations

from typing import Literal

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

    def to_dict(self) -> dict:
        d: dict = {
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

    def to_dict(self) -> dict:
        return {
            "status": self.overall,
            "mcp_servers": {name: h.to_dict() for name, h in self.servers.items()},
        }
