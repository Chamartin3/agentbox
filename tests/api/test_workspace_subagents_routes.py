"""Tests for /api/workspaces/{id}/subagents routes."""

from __future__ import annotations

from typing import Any


def test_empty_subagents_list(client: Any) -> None:
    r = client.get("/api/workspaces/ws-1/subagents")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_put_and_get_subagents(client: Any) -> None:
    body = {
        "subagents": [
            {"agent_id": "agent-a", "alias": "researcher", "display_order": 0},
            {"agent_id": "agent-b", "alias": "writer", "display_order": 1},
        ],
        "actor": "tester",
    }
    r = client.put("/api/workspaces/ws-1/subagents", json=body)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [s["alias"] for s in items] == ["researcher", "writer"]

    r2 = client.get("/api/workspaces/ws-1/subagents")
    assert r2.status_code == 200
    aliases = [s["alias"] for s in r2.json()["items"]]
    assert aliases == ["researcher", "writer"]


def test_duplicate_alias_rejected(client: Any) -> None:
    body = {
        "subagents": [
            {"agent_id": "a", "alias": "dup"},
            {"agent_id": "b", "alias": "dup"},
        ]
    }
    r = client.put("/api/workspaces/ws-2/subagents", json=body)
    assert r.status_code == 400


def test_missing_alias_rejected(client: Any) -> None:
    body = {"subagents": [{"agent_id": "a", "alias": ""}]}
    r = client.put("/api/workspaces/ws-3/subagents", json=body)
    assert r.status_code == 400


def test_replace_clears_previous(client: Any) -> None:
    client.put(
        "/api/workspaces/ws-4/subagents",
        json={"subagents": [{"agent_id": "a", "alias": "one"}]},
    )
    r = client.put(
        "/api/workspaces/ws-4/subagents",
        json={"subagents": [{"agent_id": "b", "alias": "two"}]},
    )
    assert r.status_code == 200
    aliases = [s["alias"] for s in r.json()["items"]]
    assert aliases == ["two"]
