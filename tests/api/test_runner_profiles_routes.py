"""Tests for runner profile API routes.

Scenarios covered:
- POST /api/runner-profiles: create with validation
- GET /api/runner-profiles: list with filters
- GET /api/runner-profiles/{profile_id}: get/404
- PATCH /api/runner-profiles/{profile_id}: update
- DELETE /api/runner-profiles/{profile_id}: delete
- GET /api/runner-profiles/{profile_id}/stats: stats endpoint
- GET/PATCH/DELETE /api/agents/{agent_id}/runner-profile: agent binding
"""

from __future__ import annotations

from typing import Any


class TestCreateRunnerProfile:
    """POST /api/runner-profiles tests."""

    def test_create_profile_minimal(self, client: Any) -> None:
        """POST with id/name/backend → 201, body matches."""
        req = {
            "id": "my-profile",
            "name": "My Profile",
            "backend": "token",
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "my-profile"
        assert data["name"] == "My Profile"
        assert data["backend"] == "token"
        assert data["is_enabled"] is True
        assert data["is_system_default"] is False

    def test_create_profile_with_all_fields(self, client: Any) -> None:
        """POST with all optional fields."""
        req = {
            "id": "full-profile",
            "name": "Full Profile",
            "description": "A complete profile",
            "backend": "token",
            "provider": "openai",
            "model": "openai:gpt-4o",
            "timeout_seconds": 30,
            "base_url": "https://api.openai.com",
            "api_key_env": "OPENAI_API_KEY",
            "params": {"temperature": 0.7},
            "headers": {"X-Custom": "value"},
            "extra_args": ["--debug"],
            "is_enabled": True,
            "is_system_default": False,
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "full-profile"
        assert data["provider"] == "openai"
        assert data["model"] == "openai:gpt-4o"
        assert data["timeout_seconds"] == 30
        assert data["base_url"] == "https://api.openai.com"
        assert data["api_key_env"] == "OPENAI_API_KEY"
        assert data["params"]["temperature"] == 0.7
        assert data["headers"]["X-Custom"] == "value"
        assert data["extra_args"] == ["--debug"]

    def test_create_profile_invalid_backend_rejected(self, client: Any) -> None:
        """backend='bogus' → 400."""
        req = {
            "id": "bad-backend",
            "name": "Bad Backend",
            "backend": "bogus",
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        assert "unknown backend" in resp.json()["detail"].lower()

    def test_create_profile_invalid_provider_rejected(self, client: Any) -> None:
        """provider='bogus' while backend valid → 400."""
        req = {
            "id": "bad-provider",
            "name": "Bad Provider",
            "backend": "token",
            "provider": "bogus",
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        assert "unknown provider" in resp.json()["detail"].lower()

    def test_create_profile_invalid_base_url_rejected(self, client: Any) -> None:
        """base_url='ftp://x' → 400."""
        req = {
            "id": "bad-url",
            "name": "Bad URL",
            "backend": "token",
            "base_url": "ftp://invalid.com",
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        assert "http" in resp.json()["detail"].lower()

    def test_create_profile_secret_api_key_env_rejected(self, client: Any) -> None:
        """api_key_env='sk-abc...' (secret shape) → 400 with message about secret."""
        req = {
            "id": "secret-env",
            "name": "Secret Env",
            "backend": "token",
            "api_key_env": "sk-1234567890abcdefghijklmnopqrstuvwxyz",
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "secret" in detail or "looks like" in detail

    def test_create_profile_bearer_token_api_key_rejected(self, client: Any) -> None:
        """api_key_env='Bearer ...' (secret shape) → 400."""
        req = {
            "id": "bearer-env",
            "name": "Bearer Env",
            "backend": "token",
            "api_key_env": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "secret" in detail or "looks like" in detail

    def test_create_profile_too_long_api_key_env_rejected(self, client: Any) -> None:
        """api_key_env with length > 64 (too long for env var name) → 400."""
        req = {
            "id": "long-env",
            "name": "Long Env",
            "backend": "token",
            "api_key_env": "A" * 100,  # Very long, > 64
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "secret" in detail or "looks like" in detail

    def test_create_profile_invalid_api_key_env_format_rejected(self, client: Any) -> None:
        """api_key_env with invalid chars (lowercase, hyphens) → 400."""
        req = {
            "id": "invalid-env-name",
            "name": "Invalid Env Name",
            "backend": "token",
            "api_key_env": "my-key",  # lowercase + hyphens
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "env var name" in detail

    def test_create_profile_authorization_header_rejected(self, client: Any) -> None:
        """headers={'Authorization':'x'} → 400."""
        req = {
            "id": "auth-header",
            "name": "Auth Header",
            "backend": "token",
            "headers": {"Authorization": "Bearer secret"},
        }
        resp = client.post("/api/runner-profiles", json=req)
        assert resp.status_code == 400
        assert "authorization" in resp.json()["detail"].lower()

    def test_create_profile_negative_timeout_rejected(self, client: Any) -> None:
        """timeout_seconds=0 or -1 → 400."""
        for timeout in [0, -1, -10]:
            req = {
                "id": f"neg-timeout-{timeout}",
                "name": f"Negative Timeout {timeout}",
                "backend": "token",
                "timeout_seconds": timeout,
            }
            resp = client.post("/api/runner-profiles", json=req)
            assert resp.status_code == 400
            assert "positive" in resp.json()["detail"].lower()


class TestGetRunnerProfile:
    """GET /api/runner-profiles/{profile_id} tests."""

    def test_get_profile_returns_404(self, client: Any) -> None:
        """missing id → 404."""
        resp = client.get("/api/runner-profiles/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_profile_after_create(self, client: Any) -> None:
        """Create then GET returns the same profile."""
        # Create
        create_req = {
            "id": "test-profile",
            "name": "Test Profile",
            "backend": "token",
            "model": "openai:gpt-4o",
        }
        create_resp = client.post("/api/runner-profiles", json=create_req)
        assert create_resp.status_code == 201

        # Get
        get_resp = client.get("/api/runner-profiles/test-profile")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == "test-profile"
        assert data["name"] == "Test Profile"
        assert data["model"] == "openai:gpt-4o"


class TestListRunnerProfiles:
    """GET /api/runner-profiles tests."""

    def test_list_profiles_empty(self, client: Any) -> None:
        """GET with no profiles returns empty list."""
        resp = client.get("/api/runner-profiles")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_profiles_returns_created(self, client: Any) -> None:
        """Create profile, then list returns it."""
        # Create
        create_req = {
            "id": "profile-1",
            "name": "Profile 1",
            "backend": "token",
        }
        client.post("/api/runner-profiles", json=create_req)

        # List
        resp = client.get("/api/runner-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "profile-1"

    def test_list_profiles_filters_by_backend(self, client: Any) -> None:
        """Create two with different backends, GET with ?backend=... returns subset."""
        # Create pydantic_ai profile
        client.post("/api/runner-profiles", json={
            "id": "pydantic-profile",
            "name": "Pydantic Profile",
            "backend": "token",
        })

        # Create claude_code profile
        client.post("/api/runner-profiles", json={
            "id": "claude-profile",
            "name": "Claude Profile",
            "backend": "claude_code",
        })

        # Filter by pydantic_ai
        resp = client.get("/api/runner-profiles", params={"backend": "token"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "pydantic-profile"

        # Filter by claude_code
        resp = client.get("/api/runner-profiles", params={"backend": "claude_code"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "claude-profile"

    def test_list_profiles_filters_by_provider(self, client: Any) -> None:
        """Create profiles with different providers, filter by provider."""
        # Create openai profile
        client.post("/api/runner-profiles", json={
            "id": "openai-profile",
            "name": "OpenAI Profile",
            "backend": "token",
            "provider": "openai",
        })

        # Create openrouter profile
        client.post("/api/runner-profiles", json={
            "id": "openrouter-profile",
            "name": "OpenRouter Profile",
            "backend": "token",
            "provider": "openrouter",
        })

        # Filter by openai
        resp = client.get("/api/runner-profiles", params={"provider": "openai"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "openai-profile"

    def test_list_profiles_filters_by_enabled(self, client: Any) -> None:
        """Create enabled/disabled profiles, filter by enabled status."""
        # Create enabled profile
        client.post("/api/runner-profiles", json={
            "id": "enabled-profile",
            "name": "Enabled Profile",
            "backend": "token",
            "is_enabled": True,
        })

        # Create disabled profile
        client.post("/api/runner-profiles", json={
            "id": "disabled-profile",
            "name": "Disabled Profile",
            "backend": "token",
            "is_enabled": False,
        })

        # Filter by enabled
        resp = client.get("/api/runner-profiles", params={"enabled": True})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "enabled-profile"

        # Filter by disabled
        resp = client.get("/api/runner-profiles", params={"enabled": False})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "disabled-profile"


class TestPatchRunnerProfile:
    """PATCH /api/runner-profiles/{profile_id} tests."""

    def test_patch_profile_updates_fields(self, client: Any) -> None:
        """update name + model, others preserved."""
        # Create profile
        client.post("/api/runner-profiles", json={
            "id": "patch-test",
            "name": "Original Name",
            "backend": "token",
            "provider": "openai",
            "model": "openai:gpt-3.5-turbo",
        })

        # Patch
        patch_req = {
            "name": "Updated Name",
            "model": "openai:gpt-4o",
        }
        resp = client.patch("/api/runner-profiles/patch-test", json=patch_req)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        assert data["model"] == "openai:gpt-4o"
        # Others should be preserved
        assert data["backend"] == "token"
        assert data["provider"] == "openai"

    def test_patch_profile_missing_returns_404(self, client: Any) -> None:
        """PATCH nonexistent profile → 404."""
        resp = client.patch(
            "/api/runner-profiles/nonexistent",
            json={"name": "New Name"},
        )
        assert resp.status_code == 404

    def test_patch_profile_validates_backend(self, client: Any) -> None:
        """PATCH with invalid backend → 400."""
        # Create valid profile
        client.post("/api/runner-profiles", json={
            "id": "valid-profile",
            "name": "Valid",
            "backend": "token",
        })

        # Try to patch with invalid backend
        resp = client.patch(
            "/api/runner-profiles/valid-profile",
            json={"backend": "bogus"},
        )
        assert resp.status_code == 400
        assert "unknown backend" in resp.json()["detail"].lower()


class TestDeleteRunnerProfile:
    """DELETE /api/runner-profiles/{profile_id} tests."""

    def test_delete_profile_removes_it(self, client: Any) -> None:
        """DELETE then GET → 404."""
        # Create
        client.post("/api/runner-profiles", json={
            "id": "delete-test",
            "name": "Delete Test",
            "backend": "token",
        })

        # Delete
        delete_resp = client.delete("/api/runner-profiles/delete-test")
        assert delete_resp.status_code == 200

        # Try to get (should be 404)
        get_resp = client.get("/api/runner-profiles/delete-test")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_profile_returns_404(self, client: Any) -> None:
        """DELETE nonexistent profile → 404."""
        resp = client.delete("/api/runner-profiles/nonexistent")
        assert resp.status_code == 404


class TestRunnerProfileStats:
    """GET /api/runner-profiles/{profile_id}/stats tests."""

    def test_profile_stats_endpoint(self, client: Any) -> None:
        """POST profile, GET /stats returns RunnerProfileStats schema with zero counts."""
        # Create profile
        client.post("/api/runner-profiles", json={
            "id": "stats-test",
            "name": "Stats Test",
            "backend": "token",
        })

        # Get stats
        resp = client.get("/api/runner-profiles/stats-test/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["profile_id"] == "stats-test"
        assert data["runs"] == 0
        assert data["succeeded"] == 0
        assert data["failed"] == 0
        assert data["input_tokens"] == 0
        assert data["output_tokens"] == 0
        assert data["cost_usd"] is None or data["cost_usd"] == 0
        assert data["avg_duration_ms"] is None or data["avg_duration_ms"] == 0
        assert data["last_run_at"] is None

    def test_stats_missing_profile_returns_404(self, client: Any) -> None:
        """GET stats for nonexistent profile → 404."""
        resp = client.get("/api/runner-profiles/nonexistent/stats")
        assert resp.status_code == 404


class TestAgentRunnerProfileBinding:
    """GET/PATCH/DELETE /api/agents/{agent_id}/runner-profile tests."""

    def test_bind_agent_to_profile_and_get(self, client: Any) -> None:
        """PATCH /api/agents/{aid}/runner-profile then GET returns the profile."""
        # Create profile
        client.post("/api/runner-profiles", json={
            "id": "binding-test-profile",
            "name": "Binding Test Profile",
            "backend": "token",
        })

        # Bind to agent
        bind_resp = client.patch(
            "/api/agents/test-agent/runner-profile",
            json={"runner_profile_id": "binding-test-profile"},
        )
        assert bind_resp.status_code == 200
        data = bind_resp.json()
        assert data["id"] == "binding-test-profile"

        # Get binding
        get_resp = client.get("/api/agents/test-agent/runner-profile")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == "binding-test-profile"

    def test_bind_agent_to_nonexistent_profile_returns_404(self, client: Any) -> None:
        """PATCH with nonexistent profile_id → 404."""
        resp = client.patch(
            "/api/agents/test-agent/runner-profile",
            json={"runner_profile_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_get_agent_runner_profile_not_bound_returns_404(self, client: Any) -> None:
        """GET agent with no binding → 404."""
        resp = client.get("/api/agents/unbound-agent/runner-profile")
        assert resp.status_code == 404
        assert "no runner profile bound" in resp.json()["detail"].lower()

    def test_clear_agent_binding(self, client: Any) -> None:
        """DELETE then GET → 404."""
        # Create and bind profile
        client.post("/api/runner-profiles", json={
            "id": "clear-test-profile",
            "name": "Clear Test Profile",
            "backend": "token",
        })
        client.patch(
            "/api/agents/test-agent-2/runner-profile",
            json={"runner_profile_id": "clear-test-profile"},
        )

        # Delete binding
        delete_resp = client.delete("/api/agents/test-agent-2/runner-profile")
        assert delete_resp.status_code == 200

        # Try to get (should be 404)
        get_resp = client.get("/api/agents/test-agent-2/runner-profile")
        assert get_resp.status_code == 404

    def test_change_agent_binding(self, client: Any) -> None:
        """Bind agent to one profile, then change to another."""
        # Create two profiles
        client.post("/api/runner-profiles", json={
            "id": "profile-a",
            "name": "Profile A",
            "backend": "token",
            "model": "openai:gpt-4o",
        })
        client.post("/api/runner-profiles", json={
            "id": "profile-b",
            "name": "Profile B",
            "backend": "claude_code",
        })

        # Bind to profile-a
        resp1 = client.patch(
            "/api/agents/change-test/runner-profile",
            json={"runner_profile_id": "profile-a"},
        )
        assert resp1.json()["id"] == "profile-a"

        # Change to profile-b
        resp2 = client.patch(
            "/api/agents/change-test/runner-profile",
            json={"runner_profile_id": "profile-b"},
        )
        assert resp2.json()["id"] == "profile-b"

        # Verify final binding
        resp3 = client.get("/api/agents/change-test/runner-profile")
        assert resp3.json()["id"] == "profile-b"


class TestApiNeverReturnsSecrets:
    """Verify API responses never include resolved secret values."""

    def test_api_returns_env_var_name_not_value(self, client: Any, monkeypatch: Any) -> None:
        """Set api_key_env and read profile back; ensure response contains name only, no resolved value."""
        # Set an env var with a secret
        monkeypatch.setenv("TEST_API_KEY", "secret-key-123")

        # Create profile with api_key_env
        req = {
            "id": "secret-test",
            "name": "Secret Test",
            "backend": "token",
            "api_key_env": "TEST_API_KEY",
        }
        client.post("/api/runner-profiles", json=req)

        # Get profile
        resp = client.get("/api/runner-profiles/secret-test")
        assert resp.status_code == 200
        data = resp.json()
        # Should have the name, not the resolved value
        assert data["api_key_env"] == "TEST_API_KEY"
        # The secret should NOT be in the response
        assert "secret-key-123" not in str(data)
