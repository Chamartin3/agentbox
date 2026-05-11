"""Tests for the canonical workspaces registry (create/list/delete)."""

from __future__ import annotations

from typing import Any


def test_create_and_list_workspace(client: Any) -> None:
    r = client.post("/api/workspaces", json={"name": "ws-new", "description": "hello"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "ws-new"
    assert body["description"] == "hello"
    assert body["source"] == "db"

    r2 = client.get("/api/workspaces")
    assert r2.status_code == 200
    names = [w["name"] for w in r2.json()]
    assert "ws-new" in names
    row = next(w for w in r2.json() if w["name"] == "ws-new")
    assert row["source"] == "db"
    assert row["agent_count"] == 0


def test_create_duplicate_returns_409(client: Any) -> None:
    client.post("/api/workspaces", json={"name": "ws-dup"})
    r = client.post("/api/workspaces", json={"name": "ws-dup"})
    assert r.status_code == 409


def test_delete_cascade_removes_satellite_rows(client: Any) -> None:
    """Creating subagents for a workspace then deleting it should purge
    both the registry entry and the subagent rows. Before the registry
    existed, deleting from the manifest alone left phantom rows."""
    # Subagent insert auto-creates workspace_id rows in the satellite
    # table. Backfill-on-boot would normally surface the registry entry,
    # but here we create it explicitly so we control the assertion path.
    client.post("/api/workspaces", json={"name": "ws-del"})
    client.put(
        "/api/workspaces/ws-del/subagents",
        json={"subagents": [{"agent_id": "a", "alias": "x"}]},
    )

    r = client.delete("/api/workspaces/by-name/ws-del")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] == "ws-del"
    assert body["counts"]["workspaces"] == 1
    assert body["counts"].get("workspace_subagents", 0) >= 1

    # Gone from registry
    names = [w["name"] for w in client.get("/api/workspaces").json()]
    assert "ws-del" not in names

    # Subagent rows are gone too
    subs = client.get("/api/workspaces/ws-del/subagents").json()
    assert subs == {"items": []}


def test_delete_unknown_returns_404(client: Any) -> None:
    r = client.delete("/api/workspaces/by-name/does-not-exist")
    assert r.status_code == 404
