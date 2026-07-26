"""Adding a global MCP server probes it on save (plan: probe-on-add).

The upsert endpoint spawns/connects the server and reports whether it
could actually run, so a broken command is surfaced at add-time instead
of being discovered later on the settings page.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_upsert_rejects_broken_command(client: TestClient) -> None:
    # A command that exits immediately (no MCP handshake) must be rejected and
    # never added to the list.
    r = client.put(
        "/api/project/mcp-servers/broken",
        json={"name": "broken", "command": ["false"], "transport": "stdio"},
    )
    assert r.status_code == 422
    assert "failed to run" in r.json()["detail"]
    # Rejected server is absent from the list.
    listed = client.get("/api/project/mcp-servers").json()["servers"]
    assert not any(s["name"] == "broken" for s in listed)


def test_force_saves_broken_command(client: TestClient) -> None:
    # ?force=true is the escape hatch: it saves despite the probe failure.
    r = client.put(
        "/api/project/mcp-servers/broken?force=true",
        json={"name": "broken", "command": ["false"], "transport": "stdio"},
    )
    assert r.status_code == 200
    assert r.json()["error"] is not None
    listed = client.get("/api/project/mcp-servers").json()["servers"]
    assert any(s["name"] == "broken" for s in listed)
