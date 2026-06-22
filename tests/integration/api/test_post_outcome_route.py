"""Tests for POST /api/runs/{run_id}/post_outcome."""

from __future__ import annotations

import json
from typing import Any

import agentbox.api.deps as deps


def _seed_run(store: Any, *, ok: bool = True) -> str:
    rid = store.create_run(
        agent_id="test-agent",
        input_="hello",
        workdir="/tmp/wd",
        transcript_path="/tmp/t.jsonl",
    )
    store.finish_run(rid, ok=ok)
    return rid


def test_post_outcome_ok(client: Any, isolated_data_dir: Any) -> None:
    store = deps.get_store()
    rid = _seed_run(store)

    resp = client.post(f"/api/runs/{rid}/post_outcome", json={"status": "ok"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["post_status"] == "ok"

    rec = store.get_run(rid)
    assert rec is not None
    assert rec.post_status == "ok"
    assert rec.post_errors is None


def test_post_outcome_validation_fail(client: Any, isolated_data_dir: Any) -> None:
    store = deps.get_store()
    rid = _seed_run(store, ok=True)

    errors = [
        {
            "loc": ["keywords", 0, "category"],
            "msg": "Input should be 'technical_skill'",
            "type": "literal_error",
        },
        {"loc": ["keywords", 1, "name"], "msg": "Field required", "type": "missing"},
    ]
    resp = client.post(
        f"/api/runs/{rid}/post_outcome",
        json={"status": "fail", "error_kind": "validation", "errors": errors},
    )
    assert resp.status_code == 200
    assert resp.json()["post_status"] == "fail"

    rec = store.get_run(rid)
    assert rec is not None
    assert rec.post_status == "fail"
    assert rec.post_errors is not None

    parsed = json.loads(rec.post_errors)
    assert parsed["error_kind"] == "validation"
    assert len(parsed["errors"]) == 2
    assert parsed["errors"][0]["loc"] == ["keywords", 0, "category"]


def test_post_outcome_unknown_run(client: Any, isolated_data_dir: Any) -> None:
    resp = client.post("/api/runs/nonexistent/post_outcome", json={"status": "ok"})
    assert resp.status_code == 404
