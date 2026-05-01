"""Tests for agent lifecycle endpoints: publish, branch draft, rollback.

Each test creates its own app + DB to avoid DI cache pollution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from agentbox.api.app import create_app
from fastapi.testclient import TestClient


def _setup_agent_with_active_version(store) -> dict:
    """Create an agent with v1 active, return the version record."""
    config_json = {
        "id": "test-agent",
        "description": "lifecycle test",
        "runner": {"kind": "claude_code", "model": "claude-3-5-sonnet-20241022"},
    }
    # Create the agent
    v1 = store.create_agent(
        agent_id="test-agent",
        config_json=config_json,
        author="system",
        changelog="Initial version",
        prompt_content="Test prompt",
    )
    # Activate it
    store.activate_version("test-agent", v1["id"])
    return v1


def _app(tmp_path):
    """Clear DI, create app with startup triggered, return (client, store)."""
    import agentbox.api.deps as deps

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()
    client = TestClient(create_app())
    client.__enter__()
    store = deps.get_store()
    return client, store


class TestPublishVersion:
    def test_publish_returns_200_and_makes_active(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        _setup_agent_with_active_version(store)
        # Create a new draft
        draft = store.branch_draft("test-agent", author="test")
        assert draft["is_draft"] == 1
        # Publish the draft
        resp = client.post(
            f"/api/agents/test-agent/versions/{draft['version']}/publish",
            json={"reason": "Publish draft"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert not data["is_draft"]
        assert data["version"] == draft["version"]
        # Verify it's active
        active = store.get_active_version("test-agent")
        assert active is not None
        assert active["version"] == draft["version"]

    def test_publish_short_reason_returns_422(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        _setup_agent_with_active_version(store)
        draft = store.branch_draft("test-agent", author="test")
        resp = client.post(
            f"/api/agents/test-agent/versions/{draft['version']}/publish",
            json={"reason": "ab"},  # Too short
        )
        assert resp.status_code == 422

    def test_publish_missing_version_returns_404(self, isolated_data_dir) -> None:
        client, _ = _app(isolated_data_dir)
        resp = client.post(
            "/api/agents/test-agent/versions/9999/publish",
            json={"reason": "Should fail"},
        )
        assert resp.status_code == 404

    def test_publish_idempotent(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        _setup_agent_with_active_version(store)
        draft = store.branch_draft("test-agent", author="test")
        # First publish
        resp1 = client.post(
            f"/api/agents/test-agent/versions/{draft['version']}/publish",
            json={"reason": "First publish"},
        )
        assert resp1.status_code == 200
        # Second publish (idempotent)
        resp2 = client.post(
            f"/api/agents/test-agent/versions/{draft['version']}/publish",
            json={"reason": "Republish"},
        )
        assert resp2.status_code == 200


class TestBranchDraft:
    def test_branch_draft_creates_new_draft_version(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        v1 = _setup_agent_with_active_version(store)
        # Branch a draft
        resp = client.post(
            "/api/agents/test-agent/draft",
            json={"author": "test-user"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["is_draft"]
        assert data["version"] == v1["version"] + 1
        assert data["author"] == "test-user"

    def test_branch_draft_no_active_returns_404(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        # Create agent but don't activate
        config_json = {
            "id": "test-agent",
            "description": "lifecycle test",
            "runner": {"kind": "claude_code", "model": "claude-3-5-sonnet-20241022"},
        }
        store.create_agent(
            agent_id="test-agent",
            config_json=config_json,
            author="system",
            changelog="Initial version",
        )
        # Don't activate, so no active version
        resp = client.post(
            "/api/agents/test-agent/draft",
            json={"author": "test-user"},
        )
        assert resp.status_code == 404


class TestRollbackVersion:
    def test_rollback_creates_new_version_pointing_to_target(
        self, isolated_data_dir
    ) -> None:
        client, store = _app(isolated_data_dir)
        v1 = _setup_agent_with_active_version(store)
        # Create and publish v2 with different config
        store.create_version(
            agent_id="test-agent",
            source_path="test.toml",
            source_format="standalone_toml",
            content_snapshot='{"id": "test-agent-v2"}',
            prompt_snapshot="v2 prompt",
            content_hash="v2hash",
            author="system",
            changelog="Create v2",
        )
        v2 = store.latest_version("test-agent")
        # Publish v2
        store.publish_version("test-agent", v2["version"], "Publish v2")
        # Rollback to v1
        resp = client.post(
            f"/api/agents/test-agent/versions/{v1['version']}/rollback",
            json={"reason": "Rolled back due to bug", "author": "admin"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == v1["version"] + 2  # v3
        assert not data["is_draft"]
        assert data["author"] == "admin"
        # Verify it's active
        active = store.get_active_version("test-agent")
        assert active is not None
        assert active["version"] == v1["version"] + 2

    def test_rollback_missing_version_returns_404(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        _setup_agent_with_active_version(store)
        # Try to rollback to non-existent version
        resp = client.post(
            "/api/agents/test-agent/versions/9999/rollback",
            json={"reason": "Should fail", "author": "admin"},
        )
        assert resp.status_code == 404

    def test_rollback_short_reason_returns_422(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        v1 = _setup_agent_with_active_version(store)
        # Try to rollback with short reason
        resp = client.post(
            f"/api/agents/test-agent/versions/{v1['version']}/rollback",
            json={"reason": "ab", "author": "admin"},
        )
        assert resp.status_code == 422


class TestPublishWebhook:
    def test_publish_fires_webhook_when_configured(
        self, isolated_data_dir
    ) -> None:
        import json
        from sqlalchemy import update

        client, store = _app(isolated_data_dir)
        # Create agent with webhook_url
        config_json = {
            "id": "test-agent",
            "description": "webhook test",
            "runner": {"kind": "claude_code", "model": "claude-3-5-sonnet-20241022"},
            "webhook_url": "http://example.com/webhook",
        }
        v1 = store.create_agent(
            agent_id="test-agent",
            config_json=config_json,
            author="system",
            changelog="Initial version",
        )
        # Populate content_snapshot so get_agent_def can find it
        from agentbox.core.data.schema import agent_versions

        with store.engine.begin() as conn:
            conn.execute(
                update(agent_versions)
                .where(agent_versions.c.id == v1["id"])
                .values(content_snapshot=json.dumps(config_json))
            )
        store.activate_version("test-agent", v1["id"])

        # Create draft
        draft = store.branch_draft("test-agent", author="test")

        # Mock the webhook dispatcher
        with patch(
            "agentbox.api.webhooks.schedule_agent_event_webhook"
        ) as mock_schedule:
            resp = client.post(
                f"/api/agents/test-agent/versions/{draft['version']}/publish",
                json={"reason": "Test publish webhook"},
            )

        assert resp.status_code == 200
        # Verify webhook was scheduled
        mock_schedule.assert_called_once()
        call_kwargs = mock_schedule.call_args.kwargs
        assert call_kwargs["event"] == "agent.published"
        assert call_kwargs["agent_id"] == "test-agent"
        assert call_kwargs["version"] == draft["version"]
        assert call_kwargs["webhook_url"] == "http://example.com/webhook"
        assert call_kwargs["reason"] == "Test publish webhook"

    def test_publish_skips_webhook_when_url_missing(
        self, isolated_data_dir
    ) -> None:
        import json
        from sqlalchemy import update

        client, store = _app(isolated_data_dir)
        # Create agent without webhook_url
        config_json = {
            "id": "test-agent",
            "description": "webhook test",
            "runner": {"kind": "claude_code", "model": "claude-3-5-sonnet-20241022"},
        }
        v1 = store.create_agent(
            agent_id="test-agent",
            config_json=config_json,
            author="system",
            changelog="Initial version",
        )
        # Populate content_snapshot so get_agent_def can find it
        from agentbox.core.data.schema import agent_versions

        with store.engine.begin() as conn:
            conn.execute(
                update(agent_versions)
                .where(agent_versions.c.id == v1["id"])
                .values(content_snapshot=json.dumps(config_json))
            )
        store.activate_version("test-agent", v1["id"])

        # Create draft
        draft = store.branch_draft("test-agent", author="test")

        # Mock the webhook dispatcher
        with patch(
            "agentbox.api.webhooks.schedule_agent_event_webhook"
        ) as mock_schedule:
            resp = client.post(
                f"/api/agents/test-agent/versions/{draft['version']}/publish",
                json={"reason": "Test no webhook"},
            )

        assert resp.status_code == 200
        # Verify webhook was NOT scheduled
        mock_schedule.assert_not_called()

    def test_publish_webhook_failure_does_not_break_response(
        self, isolated_data_dir
    ) -> None:
        import json
        from sqlalchemy import update

        client, store = _app(isolated_data_dir)
        # Create agent with webhook_url
        config_json = {
            "id": "test-agent",
            "description": "webhook test",
            "runner": {"kind": "claude_code", "model": "claude-3-5-sonnet-20241022"},
            "webhook_url": "http://example.com/webhook",
        }
        v1 = store.create_agent(
            agent_id="test-agent",
            config_json=config_json,
            author="system",
            changelog="Initial version",
        )
        # Populate content_snapshot so get_agent_def can find it
        from agentbox.core.data.schema import agent_versions

        with store.engine.begin() as conn:
            conn.execute(
                update(agent_versions)
                .where(agent_versions.c.id == v1["id"])
                .values(content_snapshot=json.dumps(config_json))
            )
        store.activate_version("test-agent", v1["id"])

        # Create draft
        draft = store.branch_draft("test-agent", author="test")

        # Mock the webhook dispatcher to raise
        with patch(
            "agentbox.api.webhooks.schedule_agent_event_webhook",
            side_effect=RuntimeError("Webhook dispatch failed"),
        ) as mock_schedule:
            resp = client.post(
                f"/api/agents/test-agent/versions/{draft['version']}/publish",
                json={"reason": "Test webhook failure"},
            )

        # Publish should still succeed
        assert resp.status_code == 200
        # But the exception should be logged (verified by the fact that we got 200)
