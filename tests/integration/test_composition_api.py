"""API tests for composition-related routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_agent(isolated_data_dir: Path) -> Any:
    import agentbox.api.deps as deps
    from agentbox.api.app import create_app
    from fastapi.testclient import TestClient

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()

    # Create a minimal agent with composition
    agents_dir = isolated_data_dir / "agents" / "test.compose"
    agents_dir.mkdir(parents=True)
    (agents_dir / "agent.toml").write_text(
        'id = "test.compose"\n[composition]\nsystem_prompt = "prompts/system.md"\n',
        encoding="utf-8",
    )
    prompts = agents_dir / "prompts"
    prompts.mkdir()
    (prompts / "system.md").write_text("You are {role}.", encoding="utf-8")

    manifest = isolated_data_dir / "manifest.toml"
    manifest.write_text(
        'project = "test"\nagents_dir = "agents"\n',
        encoding="utf-8",
    )

    with TestClient(create_app()) as c:
        yield c

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()


class TestCreateRunWithVariables:
    def test_create_run_with_variables(self, client_with_agent: TestClient) -> None:
        resp = client_with_agent.post(
            "/api/runs",
            json={
                "agent": "test.compose",
                "variables": {"role": "helpful", "user_message": "hello"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data

    def test_create_run_legacy_input_warns(self, client_with_agent: TestClient) -> None:
        resp = client_with_agent.post(
            "/api/runs",
            json={
                "agent": "test.compose",
                "input": "legacy input",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data

    def test_create_run_missing_body_field(self, client_with_agent: TestClient) -> None:
        resp = client_with_agent.post(
            "/api/runs",
            json={
                "agent": "test.compose",
            },
        )
        assert resp.status_code == 422


class TestSnapshotEndpoint:
    def test_snapshot_run(self, client_with_agent: TestClient) -> None:
        # Create an embedded run
        resp = client_with_agent.post(
            "/api/runs",
            json={
                "agent": "test.compose",
                "variables": {"role": "helpful", "user_message": "hello"},
                "runner_embedded": True,
            },
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        # Post snapshot
        resp = client_with_agent.post(
            f"/api/runs/{run_id}/snapshot",
            json={
                "rendered_prompt": {"system": "sys", "user": "usr", "schema": None},
                "variables": {"role": "helpful"},
                "response_raw": '{"ok": true}',
                "validation_status": "ok",
                "validation_errors": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify run is finalized
        resp = client_with_agent.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        run_data = resp.json()["run"]
        assert run_data["status"] == "ok"
        assert run_data["validation_status"] == "ok"

    def test_snapshot_unknown_run(self, client_with_agent: TestClient) -> None:
        resp = client_with_agent.post(
            "/api/runs/unknown/snapshot",
            json={
                "rendered_prompt": {"system": "s", "user": "u"},
                "variables": {},
                "response_raw": "x",
                "validation_status": "ok",
                "validation_errors": [],
            },
        )
        assert resp.status_code == 404

    def test_snapshot_with_composition_snapshot(
        self, client_with_agent: TestClient
    ) -> None:
        # Create an embedded run
        resp = client_with_agent.post(
            "/api/runs",
            json={
                "agent": "test.compose",
                "variables": {"role": "helpful", "user_message": "hello"},
                "runner_embedded": True,
            },
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        # Post snapshot with composition_snapshot
        resp = client_with_agent.post(
            f"/api/runs/{run_id}/snapshot",
            json={
                "rendered_prompt": {"system": "sys", "user": "usr", "schema": None},
                "variables": {"role": "helpful"},
                "response_raw": '{"ok": true}',
                "validation_status": "ok",
                "validation_errors": [],
                "composition_snapshot": {
                    "bundle_sha": "abc123",
                    "schema_sha": "def456",
                    "references": [{"path": "shared://drafting/rules.md"}],
                },
            },
        )
        assert resp.status_code == 200

        # Verify run record includes composition_snapshot
        resp = client_with_agent.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        run_data = resp.json()["run"]
        assert run_data["status"] == "ok"
        import json as _json

        snap = _json.loads(run_data["composition_snapshot"])
        assert snap["bundle_sha"] == "abc123"
        assert snap["schema_sha"] == "def456"
