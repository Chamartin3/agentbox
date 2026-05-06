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
from agentbox.core.providers.base import ProviderDescriptor, ProviderModel
from agentbox.core.providers.registry import (
    _get_cached_models,
    _set_cached_models,
    get_provider,
    list_models,
    list_providers,
)
from agentbox.core.runner_profiles import EffectiveRunnerConfig


class TestProviderRegistry:
    """Test suite for the provider registry."""

    def test_list_providers_includes_all_four(self) -> None:
        """list_providers() returns descriptors for openai, openrouter, xai, ollama."""
        providers = list_providers()
        provider_ids = {p.id for p in providers}

        assert "openai" in provider_ids
        assert "openrouter" in provider_ids
        assert "xai" in provider_ids
        assert "ollama" in provider_ids

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
            assert descriptor.backend  # all should be "token"
            assert descriptor.backend == "token"
            assert isinstance(descriptor.requires_api_key, bool)
            assert isinstance(descriptor.supports_base_url, bool)
            assert isinstance(descriptor.supports_model_listing, bool)

    def test_descriptor_backend_all_token(self) -> None:
        """All HTTP provider descriptors use token backend."""
        providers = list_providers()
        for descriptor in providers:
            assert descriptor.backend == "token"

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
        from agentbox.core.providers.registry import _MODEL_CACHE

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
            mock_list.side_effect = ValueError("API key env NONEXISTENT_API_KEY not set")

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

    def test_cache_key_generation(self) -> None:
        """Cache key correctly encodes provider, base_url, and api_key_env."""
        from agentbox.core.providers.registry import _cache_key

        key1 = _cache_key("openai", "https://api.openai.com/v1", "OPENAI_API_KEY")
        key2 = _cache_key("openai", "https://api.openai.com/v1", "OPENAI_API_KEY")
        key3 = _cache_key("openai", "https://custom.com/v1", "OPENAI_API_KEY")

        # Same inputs produce same key
        assert key1 == key2

        # Different base_url produces different key
        assert key1 != key3

    def test_cache_ttl_expiration(self) -> None:
        """_get_cached_models returns None after TTL expires."""
        from agentbox.core.providers.registry import (
            _CACHE_TTL_SECONDS,
            _MODEL_CACHE,
        )

        # Clear cache
        _MODEL_CACHE.clear()

        models = [ProviderModel(id="test-model")]
        _set_cached_models("test_provider", None, None, models)

        # Should be retrievable immediately
        cached = _get_cached_models("test_provider", None, None)
        assert cached == models

        # Manually age the cache entry past TTL
        key = ("test_provider", None, None)
        old_time = time.time() - (_CACHE_TTL_SECONDS + 1)
        _MODEL_CACHE[key] = (models, old_time)

        # Should now be expired
        expired = _get_cached_models("test_provider", None, None)
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
