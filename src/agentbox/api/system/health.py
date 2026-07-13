from __future__ import annotations

from typing import TypedDict, NotRequired

from fastapi import APIRouter

from agentbox.api.deps import get_mcp_registry
from agentbox.core.data import McpServerHealthDict

router = APIRouter(tags=["health"])


class HealthResult(TypedDict):
    """Health status response envelope."""

    ok: bool
    version: str
    mcp_servers: NotRequired[dict[str, McpServerHealthDict]]
    status: NotRequired[str]
    mcp_error: NotRequired[str]


@router.get("/health")
def health() -> HealthResult:
    """Aggregate health including MCP server statuses."""
    base: HealthResult = {"ok": True, "version": "0.1.0"}

    try:
        registry = get_mcp_registry()
        report = registry.health_report()
        mcp_servers = report.to_dict()
        base["mcp_servers"] = mcp_servers["mcp_servers"]
        base["status"] = mcp_servers["status"]
        base["ok"] = mcp_servers["status"] != "unavailable"
    except Exception as exc:
        base["mcp_error"] = str(exc)

    return base


@router.get("/api/health")
def api_health() -> HealthResult:
    return health()
