"""Tests for /api/mcp routes — list servers, list tools per server."""

from __future__ import annotations

from typing import Any


def test_list_servers_returns_list(client: Any) -> None:
    resp = client.get("/api/mcp/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert "servers" in data
    assert "overall_status" in data


def test_get_server_tools_not_found(client: Any) -> None:
    resp = client.get("/api/mcp/servers/nonexistent/tools")
    assert resp.status_code == 404


def test_get_server_groups_not_found(client: Any) -> None:
    resp = client.get("/api/mcp/servers/nonexistent/groups")
    assert resp.status_code == 404


def test_list_servers_shape(client: Any) -> None:
    resp = client.get("/api/mcp/servers")
    data = resp.json()
    for server in data["servers"]:
        assert "name" in server
        assert "status" in server
        assert "tool_count" in server
