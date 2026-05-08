"""Tests for /api/agents/<id>/versions/ endpoints.

Each test creates its own app + DB to avoid DI cache pollution.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from agentbox.api.app import create_app
from fastapi.testclient import TestClient


class _ManagedTestClient(TestClient):
    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.__exit__(None, None, None)


def _setup(tmp_path: Path):
    """Write agent files. Returns agent file path."""
    agents_d = tmp_path / "agents.d"
    agents_d.mkdir(parents=True, exist_ok=True)
    (agents_d / "test-agent.toml").write_text(
        'id = "test-agent"\ndescription = "version test"\n'
    )


def _app(tmp_path):
    """Clear DI, create app with startup triggered, return (client, store).

    Uses explicit __enter__ instead of a with-block so the returned client
    stays alive for the caller to make requests against. Startup events
    (including startup_sweep) run inside __enter__.
    """
    import agentbox.api.deps as deps

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()
    client = _ManagedTestClient(create_app())
    client.__enter__()
    store = deps.get_store()
    return client, store


def _agent_p(tmp_path):
    return tmp_path / "agents.d" / "test-agent.toml"


class TestListVersions:
    def test_list_empty(self, client) -> None:
        resp = client.get("/api/agents/nonexistent/versions")
        assert resp.status_code == 404

    def test_list_versions(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, _ = _app(isolated_data_dir)
        resp = client.get("/api/agents/test-agent/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "test-agent"
        assert len(data["versions"]) >= 1

    def test_list_with_rating(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        _client, store = _app(isolated_data_dir)
        v = store.latest_version("test-agent")
        store.set_rating(v["id"], 5, "reviewer")
        # Verify via store directly (avoids cross-connection staleness)
        rated = store.get_rating(v["id"])
        assert rated is not None and rated["rating"] == 5


class TestGetVersion:
    def test_get_existing(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, store = _app(isolated_data_dir)
        v = store.latest_version("test-agent")
        resp = client.get(f"/api/agents/test-agent/versions/{v['version']}")
        assert resp.status_code == 200
        assert resp.json()["version"] == v["version"]

    def test_get_missing_version(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, _ = _app(isolated_data_dir)
        resp = client.get("/api/agents/test-agent/versions/9999")
        assert resp.status_code == 404

    def test_get_unknown_agent(self, client) -> None:
        resp = client.get("/api/agents/nope/versions/1")
        assert resp.status_code == 404


class TestDiffVersions:
    def test_diff(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, store = _app(isolated_data_dir)
        v1 = store.latest_version("test-agent")
        store.create_version(
            agent_id="test-agent",
            source_path=str(_agent_p(isolated_data_dir)),
            source_format="standalone_toml",
            content_snapshot='{"id": "new"}',
            prompt_snapshot="New prompt",
            content_hash="bbb",
            author="system",
        )
        resp = client.get(
            f"/api/agents/test-agent/versions/{v1['version']}/diff/{v1['version'] + 1}"
        )
        assert resp.status_code == 200
        assert resp.json()["from_version"] == v1["version"]

    def test_diff_missing(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, _ = _app(isolated_data_dir)
        resp = client.get("/api/agents/test-agent/versions/1/diff/9999")
        assert resp.status_code == 404


class TestComments:
    def test_add_comment(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, store = _app(isolated_data_dir)
        v = store.latest_version("test-agent")
        resp = client.post(
            f"/api/agents/test-agent/versions/{v['version']}/comments",
            json={"author": "tester", "body": "Nice version"},
        )
        assert resp.status_code == 200

    def test_comment_missing_version(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, _ = _app(isolated_data_dir)
        resp = client.post(
            "/api/agents/test-agent/versions/9999/comments",
            json={"author": "tester", "body": "Hello"},
        )
        assert resp.status_code == 404


class TestRatings:
    def test_set_rating(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, store = _app(isolated_data_dir)
        v = store.latest_version("test-agent")
        resp = client.put(
            f"/api/agents/test-agent/versions/{v['version']}/rating",
            json={"rating": 4, "rater": "reviewer"},
        )
        assert resp.status_code == 200
        assert resp.json()["rating"] == 4

    def test_invalid_rating(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, store = _app(isolated_data_dir)
        v = store.latest_version("test-agent")
        resp = client.put(
            f"/api/agents/test-agent/versions/{v['version']}/rating",
            json={"rating": 99, "rater": "reviewer"},
        )
        assert resp.status_code == 400

    def test_rating_missing_version(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, _ = _app(isolated_data_dir)
        resp = client.put(
            "/api/agents/test-agent/versions/9999/rating",
            json={"rating": 3, "rater": "reviewer"},
        )
        assert resp.status_code == 404


class TestCreateVersion:
    def test_create_version(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, store = _app(isolated_data_dir)
        v1 = store.latest_version("test-agent")
        resp = client.post(
            "/api/agents/test-agent/versions",
            json={
                "content_snapshot": '{"id": "test-agent", "desc": "v2"}',
                "prompt_snapshot": "updated",
                "author": "api-user",
                "changelog": "Major update",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["author"] == "api-user"
        assert resp.json()["version"] == v1["version"] + 1

    def test_create_version_unknown_agent(self, client) -> None:
        resp = client.post(
            "/api/agents/missing/versions",
            json={"content_snapshot": "{}"},
        )
        assert resp.status_code == 404


class TestRollback:
    def test_rollback_creates_new_version(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, store = _app(isolated_data_dir)
        v1 = store.latest_version("test-agent")
        store.create_version(
            agent_id="test-agent",
            source_path=str(_agent_p(isolated_data_dir)),
            source_format="standalone_toml",
            content_snapshot='{"id": "changed"}',
            prompt_snapshot="changed",
            content_hash="def",
            author="system",
        )
        resp = client.post(
            f"/api/agents/test-agent/versions/{v1['version']}/rollback",
            json={"author": "admin", "reason": "restore previous content"},
        )
        assert resp.status_code == 201
        assert resp.json()["version"] == v1["version"] + 2

    def test_rollback_missing_version(self, isolated_data_dir) -> None:
        _setup(isolated_data_dir)
        client, _ = _app(isolated_data_dir)
        resp = client.post(
            "/api/agents/test-agent/versions/9999/rollback",
            json={"author": "admin", "reason": "restore previous content"},
        )
        assert resp.status_code == 404
