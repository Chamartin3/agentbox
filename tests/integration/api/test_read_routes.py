"""Smoke-level coverage for the read-side HTTP API.

We don't exhaust every shape here — just verify the routes wire up to
their dependencies under an isolated data dir, return JSON, and don't
explode when the project has no agents/runs yet.
"""

from __future__ import annotations


def test_list_agents_empty(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/agents")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_empty(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/runs")
    assert r.status_code == 200
    body = r.json()
    # Endpoint returns either a plain list or a dict with a `runs` key —
    # accept both shapes so the test survives small response refactors.
    runs = body if isinstance(body, list) else body.get("runs", [])
    assert runs == []


def test_usage_aggregate_zero_state(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/usage")
    assert r.status_code == 200
    body = r.json()
    assert body.get("runs", 0) == 0


def test_activity_summary_default_range(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/activity/summary")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_manifest_get_on_empty_project(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/agents/export-all")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_unknown_agent_404(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/agents/does-not-exist")
    assert r.status_code == 404
