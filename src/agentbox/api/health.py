from __future__ import annotations

from fastapi import APIRouter

from agentbox.api.deps import get_mcp_registry

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Aggregate health including MCP server statuses."""
    base = {"ok": True, "version": "0.1.0"}

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
def api_health() -> dict:
    return health()
