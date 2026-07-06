"""Tests for startup resilience — ok, degraded, unavailable states."""

from __future__ import annotations

import json
from pathlib import Path

from agentbox.core.workspaces.mcp.client.health import McpHealthReport, ServerHealth
from agentbox.core.workspaces.mcp.client.registry import McpRegistry


def test_all_servers_ok(tmp_path: Path) -> None:
    cache_dir = tmp_path / "mcp_cache"
    registry = McpRegistry(cache_dir)
    registry._health["primary"] = ServerHealth(
        status="ok", tool_count=5, fetched_at="2024-01-01T00:00:00Z"
    )
    registry._health["search"] = ServerHealth(
        status="ok", tool_count=3, fetched_at="2024-01-01T00:00:00Z"
    )
    report = registry.health_report()
    assert report.overall == "ok"
    assert len(report.servers) == 2


def test_one_server_down_with_cache_becomes_degraded(tmp_path: Path) -> None:
    cache_dir = tmp_path / "mcp_cache"
    registry = McpRegistry(cache_dir)
    registry._health["primary"] = ServerHealth(
        status="ok", tool_count=5, fetched_at="2024-01-01T00:00:00Z"
    )
    registry._health["search"] = ServerHealth(
        status="degraded",
        tool_count=3,
        fetched_at="2024-01-01T00:00:00Z",
        last_error="connection refused",
    )
    report = registry.health_report()
    assert report.overall == "degraded"


def test_all_servers_down_with_cache_becomes_degraded(tmp_path: Path) -> None:
    cache_dir = tmp_path / "mcp_cache"
    registry = McpRegistry(cache_dir)
    registry._health["primary"] = ServerHealth(
        status="degraded",
        tool_count=5,
        fetched_at="2024-01-01T00:00:00Z",
        last_error="timeout",
    )
    registry._health["search"] = ServerHealth(
        status="degraded",
        tool_count=3,
        fetched_at="2024-01-01T00:00:00Z",
        last_error="timeout",
    )
    report = registry.health_report()
    assert report.overall == "degraded"


def test_all_servers_unavailable(tmp_path: Path) -> None:
    cache_dir = tmp_path / "mcp_cache"
    registry = McpRegistry(cache_dir)
    registry._health["primary"] = ServerHealth(
        status="unavailable", last_error="connection refused"
    )
    report = registry.health_report()
    assert report.overall == "unavailable"


def test_no_servers_unavailable(tmp_path: Path) -> None:
    cache_dir = tmp_path / "mcp_cache"
    registry = McpRegistry(cache_dir)
    report = registry.health_report()
    assert report.overall == "unavailable"


def test_cache_is_loaded_on_startup(tmp_path: Path) -> None:
    cache_dir = tmp_path / "mcp_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "my-mcp.json"
    cache_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "jobpost_get_all",
                        "description": "",
                        "input_schema": None,
                    },
                    {"name": "jobpost_create", "description": "", "input_schema": None},
                ],
                "cached_at": "2024-01-01T00:00:00Z",
            }
        )
    )
    registry = McpRegistry(cache_dir)
    cached = registry._load_cache("my-mcp")
    assert cached is not None
    assert len(cached) == 2


def test_cache_corrupted_returns_none(tmp_path: Path) -> None:
    cache_dir = tmp_path / "mcp_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "my-mcp.json"
    cache_file.write_text("not-json")
    registry = McpRegistry(cache_dir)
    assert registry._load_cache("my-mcp") is None


def test_cache_missing_returns_none(tmp_path: Path) -> None:
    registry = McpRegistry(tmp_path / "mcp_cache")
    assert registry._load_cache("nonexistent") is None


def test_health_report_to_dict() -> None:
    health = ServerHealth(
        status="degraded",
        tool_count=3,
        fetched_at="2024-01-01T00:00:00Z",
        last_error="timeout",
    )
    d = health.to_dict()
    assert d["status"] == "degraded"
    assert d["tool_count"] == 3
    assert d["last_error"] == "timeout"


def test_health_report_to_dict_minimal() -> None:
    health = ServerHealth(status="unavailable", last_error="refused")
    d = health.to_dict()
    assert d["status"] == "unavailable"
    assert "fetched_at" not in d
    assert d["last_error"] == "refused"


def test_mcp_health_report_to_dict() -> None:
    servers = {
        "my-mcp": ServerHealth(
            status="ok", tool_count=5, fetched_at="2024-01-01T00:00:00Z"
        ),
    }
    report = McpHealthReport(overall="ok", servers=servers)
    d = report.to_dict()
    assert d["status"] == "ok"
    assert "my-mcp" in d["mcp_servers"]
