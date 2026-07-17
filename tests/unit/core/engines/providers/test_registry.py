"""Tests for the provider registry and model listing.

These tests verify that:
- Provider descriptors are registered and discoverable.
- Model listing caches results appropriately.
- HTTP responses are parsed correctly.
- Missing API keys are rejected.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.engines.providers import cli, registry
from agentbox.core.engines.providers.base import ProviderDescriptor, ProviderModel
from agentbox.core.engines.providers.cli import _parse_opencode_lines
from agentbox.core.engines.providers.ollama import rewrite_ollama_url
from agentbox.core.engines.providers.registry import (
    _CACHE_TTL_SECONDS,
    _MODEL_CACHE,
    _cache_key,
    _get_cached_models,
    _set_cached_models,
    get_provider,
    list_models,
    list_providers,
)


class TestProviderRegistry:
    """Test suite for the provider registry."""

    def test_list_providers_includes_builtin_providers(self) -> None:
        """list_providers() returns descriptors for built-in providers."""
        providers = list_providers()
        provider_ids = {p.id for p in providers}

        assert "openai" in provider_ids
        assert "openrouter" in provider_ids
        assert "xai" in provider_ids
        assert "ollama" in provider_ids
        assert "codex" in provider_ids
        # opencode CLI providers are dynamically discovered; only assert
        # they get registered if discovery succeeded at import time.

    def test_get_provider_returns_adapter_or_none(self) -> None:
        """get_provider() returns adapter for registered provider, None otherwise."""
        openai_adapter = get_provider("openai")
        assert openai_adapter is not None
        assert hasattr(openai_adapter, "descriptor")
        assert hasattr(openai_adapter, "list_models")

        # Non-existent provider
        none_adapter = get_provider("nonexistent")
        assert none_adapter is None

    def test_descriptor_fields_present(self) -> None:
        """Each provider descriptor has all required fields."""
        providers = list_providers()

        for descriptor in providers:
            assert isinstance(descriptor, ProviderDescriptor)
            assert descriptor.id
            assert descriptor.label
            assert descriptor.compatible_backends
            assert isinstance(descriptor.requires_api_key, bool)
            assert isinstance(descriptor.supports_base_url, bool)
            assert isinstance(descriptor.supports_model_listing, bool)

    def test_descriptor_backend_matches_provider_family(self) -> None:
        """Provider descriptors declare their owning backend family."""
        by_id = {p.id: p for p in list_providers()}
        assert by_id["openai"].backend == "token"
        assert by_id["ollama"].compatible_backends == ["token", "opencode"]
        assert by_id["codex"].backend == "codex"
        assert by_id["codex"].compatible_backends == ["codex"]

    def test_openai_descriptor_fields(self) -> None:
        """OpenAI descriptor has correct values."""
        openai_adapter = get_provider("openai")
        assert openai_adapter is not None

        desc = openai_adapter.descriptor
        assert desc.id == "openai"
        assert desc.requires_api_key is True
        assert desc.supports_base_url is True
        assert desc.supports_model_listing is True
        assert desc.default_base_url == "https://api.openai.com/v1"
        assert desc.default_api_key_env == "OPENAI_API_KEY"

    def test_ollama_descriptor_fields(self) -> None:
        """Ollama descriptor has correct values."""
        ollama_adapter = get_provider("ollama")
        assert ollama_adapter is not None

        desc = ollama_adapter.descriptor
        assert desc.id == "ollama"
        assert desc.requires_api_key is False
        assert desc.supports_base_url is True
        assert desc.supports_model_listing is True
        assert desc.default_base_url == "http://localhost:11434"
        assert desc.default_api_key_env is None

    @pytest.mark.asyncio
    async def test_list_models_caches_results(self) -> None:
        """list_models() caches results and does not call adapter twice in TTL."""
        adapter = get_provider("openai")
        assert adapter is not None

        config = EffectiveRunnerConfig(
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        )

        mock_models = [
            ProviderModel(id="gpt-4o"),
            ProviderModel(id="gpt-4-turbo"),
        ]

        # Mock the adapter's list_models method
        with patch.object(adapter, "list_models", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_models

            # First call should hit the network
            result1 = await list_models("openai", config)
            assert result1 == mock_models
            assert mock_list.call_count == 1

            # Second call within TTL should use cache
            result2 = await list_models("openai", config)
            assert result2 == mock_models
            assert mock_list.call_count == 1  # No new call

    @pytest.mark.asyncio
    async def test_list_models_refresh_bypasses_cache(self) -> None:
        """list_models() with refresh=True fetches fresh data."""
        _MODEL_CACHE.clear()  # Clear cache from previous tests
        adapter = get_provider("openai")
        assert adapter is not None

        config = EffectiveRunnerConfig(
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        )

        mock_models_v1 = [ProviderModel(id="gpt-4o")]
        mock_models_v2 = [ProviderModel(id="gpt-4o"), ProviderModel(id="gpt-4")]

        with patch.object(adapter, "list_models", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = [mock_models_v1, mock_models_v2]

            # First call
            result1 = await list_models("openai", config)
            assert result1 == mock_models_v1

            # Second call with refresh=True should bypass cache
            result2 = await list_models("openai", config, refresh=True)
            assert result2 == mock_models_v2
            assert mock_list.call_count == 2

    @pytest.mark.asyncio
    async def test_list_models_missing_api_key_raises(self) -> None:
        """list_models() raises when API key env is missing and required."""
        adapter = get_provider("openai")
        assert adapter is not None

        config = EffectiveRunnerConfig(
            base_url="https://api.openai.com/v1",
            api_key_env="NONEXISTENT_API_KEY",
        )

        # Mock to raise ValueError for missing key
        with patch.object(adapter, "list_models", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = ValueError(
                "API key env NONEXISTENT_API_KEY not set"
            )

            with pytest.raises(ValueError, match="API key env"):
                await list_models("openai", config)

    @pytest.mark.asyncio
    async def test_list_models_unknown_provider_raises(self) -> None:
        """list_models() raises for unknown provider."""
        config = EffectiveRunnerConfig()

        with pytest.raises(ValueError, match="Provider not found"):
            await list_models("nonexistent_provider", config)

    @pytest.mark.asyncio
    async def test_openai_list_models_parses_response(self) -> None:
        """OpenAI adapter parses model list response correctly."""

        adapter = get_provider("openai")
        assert adapter is not None

        config = EffectiveRunnerConfig(
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        )

        # Mock httpx.AsyncClient to return model list
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"id": "gpt-4o", "owned_by": "openai", "object": "model"},
                {"id": "gpt-4-turbo", "owned_by": "openai", "object": "model"},
                {"id": "gpt-3.5-turbo", "owned_by": "openai", "object": "model"},
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            # Note: We need to patch the os.environ to set the key
            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                models = await adapter.list_models(config)

            assert len(models) == 3
            assert models[0].id == "gpt-4o"
            assert models[1].id == "gpt-4-turbo"
            assert models[2].id == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_ollama_list_models_no_auth(self) -> None:
        """Ollama adapter lists models without authentication."""
        adapter = get_provider("ollama")
        assert adapter is not None

        config = EffectiveRunnerConfig(
            backend="token",
            base_url="http://localhost:11434",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3", "model": "llama3:latest"},
                {"name": "mistral", "model": "mistral:latest"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            models = await adapter.list_models(config)

            assert len(models) == 2
            assert models[0].id == "llama3"
            assert models[1].id == "mistral"

    @pytest.mark.asyncio
    async def test_ollama_list_models_opencode_uses_qualified_ids(self) -> None:
        """Ollama model ids are provider-qualified for the OpenCode CLI."""
        adapter = get_provider("ollama")
        assert adapter is not None

        config = EffectiveRunnerConfig(
            backend="opencode",
            base_url="http://localhost:11434",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3", "model": "llama3:latest"},
                {"name": "mistral", "model": "mistral:latest"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            models = await adapter.list_models(config)

            assert [model.id for model in models] == ["ollama/llama3", "ollama/mistral"]

    def test_refresh_opencode_providers_registers_discovered_prefixes(self) -> None:
        """refresh_opencode_providers() adds one adapter per discovered prefix.

        Verifies the namespace-collision rule: bare ``openai`` is owned by
        the HTTP adapter, so the opencode side is registered as
        ``opencode-openai``; ``ollama`` declares opencode compat so it is
        left untouched.
        """
        with patch.object(
            cli,
            "discover_opencode_providers",
            return_value=["openai", "ollama", "opencode", "opencode-go"],
        ):
            discovered = registry.refresh_opencode_providers()

        assert discovered == ["openai", "ollama", "opencode", "opencode-go"]
        # HTTP openai keeps the bare id; opencode side gets a namespaced id.
        assert isinstance(registry.get_provider("openai"), object)
        assert registry.get_provider("openai").descriptor.compatible_backends == ["token"]  # type: ignore[union-attr]
        opencode_openai = registry.get_provider("opencode-openai")
        assert opencode_openai is not None
        assert opencode_openai.descriptor.compatible_backends == ["opencode"]
        # Ollama opencode-compat adapter is preserved untouched.
        ollama = registry.get_provider("ollama")
        assert ollama is not None
        assert "opencode" in (ollama.descriptor.compatible_backends or [])
        # Bare opencode prefix registers as itself.
        bare = registry.get_provider("opencode")
        assert bare is not None
        assert isinstance(bare, cli.OpenCodeCLIAdapter)
        assert bare.cli_prefix == "opencode"

        # Restore real state for subsequent tests.
        registry.refresh_opencode_providers()

    def test_ollama_url_rewrite_swaps_localhost_inside_container(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Forcing in-container mode rewrites localhost → host.docker.internal."""
        monkeypatch.setenv("AGENTBOX_IN_CONTAINER", "1")
        monkeypatch.delenv("AGENTBOX_OLLAMA_URL_REWRITE", raising=False)

        assert (
            rewrite_ollama_url("http://localhost:11434")
            == "http://host.docker.internal:11434"
        )
        assert (
            rewrite_ollama_url("http://127.0.0.1:11434/v1")
            == "http://host.docker.internal:11434/v1"
        )
        # Non-matching host is left untouched.
        assert rewrite_ollama_url("http://ollama:11434") == "http://ollama:11434"

    def test_ollama_url_rewrite_disabled_when_env_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty AGENTBOX_OLLAMA_URL_REWRITE disables the default rewrite."""
        monkeypatch.setenv("AGENTBOX_IN_CONTAINER", "1")
        monkeypatch.setenv("AGENTBOX_OLLAMA_URL_REWRITE", "")

        assert rewrite_ollama_url("http://localhost:11434") == "http://localhost:11434"

    def test_ollama_url_rewrite_custom_map(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit override map wins over the container default."""
        monkeypatch.setenv(
            "AGENTBOX_OLLAMA_URL_REWRITE", "localhost=ollama-svc,my-host=other"
        )
        assert rewrite_ollama_url("http://localhost:11434") == "http://ollama-svc:11434"
        assert rewrite_ollama_url("http://my-host/api") == "http://other/api"

    def test_opencode_provider_parser_filters_provider(self) -> None:
        """OpenCode CLI provider adapters keep only their provider-qualified ids."""
        models = _parse_opencode_lines(
            "opencode/gpt-5\nopencode-go/qwen3.5\nopenai/gpt-5\n",
            "opencode",
        )

        assert [model.id for model in models] == ["opencode/gpt-5"]

    def test_cache_key_generation(self) -> None:
        """Cache key correctly encodes provider, base_url, api_key_env, and backend."""
        key1 = _cache_key(
            "openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "token"
        )
        key2 = _cache_key(
            "openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "token"
        )
        key3 = _cache_key("openai", "https://custom.com/v1", "OPENAI_API_KEY", "token")
        key4 = _cache_key(
            "openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "opencode"
        )

        # Same inputs produce same key
        assert key1 == key2

        # Different base_url/backend produces different key
        assert key1 != key3
        assert key1 != key4

    def test_cache_ttl_expiration(self) -> None:
        """_get_cached_models returns None after TTL expires."""
        # Clear cache
        _MODEL_CACHE.clear()

        models = [ProviderModel(id="test-model")]
        _set_cached_models("test_provider", None, None, "token", models)

        # Should be retrievable immediately
        cached = _get_cached_models("test_provider", None, None, "token")
        assert cached == models

        # Manually age the cache entry past TTL
        key = ("test_provider", None, None, "token")
        old_time = time.time() - (_CACHE_TTL_SECONDS + 1)
        _MODEL_CACHE[key] = (models, old_time)

        # Should now be expired
        expired = _get_cached_models("test_provider", None, None, "token")
        assert expired is None

        # Cleanup
        _MODEL_CACHE.clear()

    @pytest.mark.asyncio
    async def test_list_models_does_not_cache_errors(self) -> None:
        """list_models() does not cache 401/403 errors as empty success."""
        adapter = get_provider("openai")
        assert adapter is not None

        config = EffectiveRunnerConfig(
            base_url="https://api.openai.com/v1",
            api_key_env="BAD_KEY",
        )

        # First call raises 401
        with patch.object(adapter, "list_models", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = Exception("401 Unauthorized")

            with pytest.raises(Exception, match="401"):
                await list_models("openai", config)

            # Second call should NOT use cache, and adapter should be called again
            mock_list.side_effect = Exception("401 Unauthorized")
            with pytest.raises(Exception, match="401"):
                await list_models("openai", config)

            # Adapter should have been called twice (no caching of errors)
            assert mock_list.call_count == 2
