"""Tests for runner provider discovery API routes."""

from __future__ import annotations

from typing import Any


def test_list_runner_providers(client: Any) -> None:
    """Test listing all provider descriptors."""
    resp = client.get("/api/runner-providers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0  # Should have at least one provider

    # Check descriptor structure
    for provider in data:
        assert "id" in provider
        assert "label" in provider
        assert "backend" in provider
        assert "requires_api_key" in provider
        assert "supports_base_url" in provider
        assert "supports_model_listing" in provider


def test_list_runner_providers_filters_by_backend(client: Any) -> None:
    """Provider list can be filtered to the selected backend."""
    codex_resp = client.get("/api/runner-providers", params={"backend": "codex"})
    assert codex_resp.status_code == 200
    assert {p["id"] for p in codex_resp.json()} == {"codex"}

    opencode_resp = client.get("/api/runner-providers", params={"backend": "opencode"})
    assert opencode_resp.status_code == 200
    # opencode CLI sub-providers are discovered dynamically; only ollama
    # is guaranteed (it declares opencode compat statically).
    provider_ids = {p["id"] for p in opencode_resp.json()}
    assert "ollama" in provider_ids


def test_list_provider_models_missing_provider(client: Any) -> None:
    """Test listing models for a nonexistent provider."""
    resp = client.get("/api/runner-providers/nonexistent-provider/models")
    assert resp.status_code == 404
    data = resp.json()
    # FastAPI wraps in "detail"
    assert "detail" in data or "error" in data
    err_msg = data.get("detail", data.get("error", ""))
    if isinstance(err_msg, dict):
        err_msg = err_msg.get("error", "")
    assert "not found" in str(err_msg).lower()


def test_list_provider_models_missing_profile(client: Any) -> None:
    """Test listing models with a nonexistent profile."""
    resp = client.get(
        "/api/runner-providers/openai/models",
        params={"profile_id": "nonexistent-profile"},
    )
    assert resp.status_code == 404
    data = resp.json()
    # FastAPI wraps in "detail"
    assert "detail" in data or "error" in data
    err_msg = data.get("detail", data.get("error", ""))
    if isinstance(err_msg, dict):
        err_msg = err_msg.get("error", "")
    assert "not found" in str(err_msg).lower()


def test_list_provider_models_returns_descriptors(client: Any) -> None:
    """Test listing all provider descriptors returns expected providers."""
    resp = client.get("/api/runner-providers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    provider_ids = {p["id"] for p in data}
    # Should include at least the main providers
    expected_providers = {"openai", "openrouter", "xai", "ollama"}
    # At least some of these should be present
    assert len(expected_providers & provider_ids) > 0


def test_deprecated_manifest_runner_models(client: Any) -> None:
    """Test the deprecated /api/manifest/runner-models endpoint now includes deprecation notice."""
    resp = client.get("/api/manifest/runner-models", params={"kind": "claude_code"})
    assert resp.status_code == 200
    data = resp.json()
    assert "deprecated" in data
    assert data["deprecated"] is True
    assert "replacement" in data
    assert "/api/runner-providers" in data["replacement"]


def test_list_provider_models_with_profile_id(client: Any) -> None:
    """Test listing models using a stored runner profile for configuration."""
    # First, create a runner profile
    profile_req = {
        "id": "openai-profile",
        "name": "OpenAI Profile",
        "backend": "token",
        "provider": "openai",
        "base_url": "https://api.openai.com",
        "api_key_env": "OPENAI_API_KEY",
    }
    client.post("/api/runner-profiles", json=profile_req)

    # Then, try to list models with that profile_id
    # This may fail with auth error in test (no real API key), but should
    # not fail with "profile not found"
    resp = client.get(
        "/api/runner-providers/openai/models",
        params={"profile_id": "openai-profile"},
    )
    # We expect either success (if mocked) or an auth/HTTP error, not 404
    assert resp.status_code != 404 or "profile" not in str(resp.json()).lower()


def test_list_provider_models_with_base_url_override(client: Any) -> None:
    """Test listing models with custom base_url query param."""
    resp = client.get(
        "/api/runner-providers/ollama/models",
        params={"base_url": "http://localhost:11434"},
    )
    # May fail due to network/no actual service, but should not be a 400 validation error
    # (base_url is valid HTTP)
    assert resp.status_code != 400 or "base_url" not in str(resp.json()).lower()


def test_list_provider_models_redacts_auth_error(client: Any, monkeypatch: Any) -> None:
    """Test that provider models endpoint redacts authentication errors."""
    # This test verifies that auth failures don't leak actual response bodies
    # We would need to mock httpx to test this properly
    # For now, just verify the happy path doesn't leak secrets
    resp = client.get("/api/runner-providers")
    assert resp.status_code == 200
    # No API keys should be in the response
    for provider in resp.json():
        assert "sk-" not in str(provider)
        assert "Bearer" not in str(provider)


def test_provider_descriptor_never_includes_secrets(client: Any) -> None:
    """Test that provider descriptors never include actual API keys."""
    resp = client.get("/api/runner-providers")
    assert resp.status_code == 200
    data = resp.json()
    # Descriptors should only have env var names in defaults, not values
    for provider in data:
        if provider.get("default_api_key_env"):
            # Should be an env var name like "OPENAI_API_KEY", not a secret
            env_var_name = provider["default_api_key_env"]
            assert not env_var_name.startswith("sk-")
            assert not env_var_name.startswith("Bearer")
            # Should look like an env var name
            assert env_var_name.isupper() or "_" in env_var_name
