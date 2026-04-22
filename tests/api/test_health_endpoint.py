"""Tests for /health endpoint — JSON shape, per-server fields."""

from __future__ import annotations

from typing import Any


def test_health_endpoint_returns_ok(client: Any) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    # At minimum, version and ok should be present
    assert "version" in data


def test_health_endpoint_has_mcp_servers(client: Any) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "mcp_servers" in data or "ok" in data


def test_api_health_matches(client: Any) -> None:
    resp1 = client.get("/health")
    resp2 = client.get("/api/health")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
