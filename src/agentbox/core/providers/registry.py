"""Provider registry with model listing cache."""

import time
from typing import Any

from agentbox.core.providers.base import ProviderAdapter, ProviderDescriptor

# Module-level cache: (provider_id, base_url, api_key_env) -> (models, timestamp)
_MODEL_CACHE: dict[tuple[str, str | None, str | None], tuple[Any, float]] = {}
_CACHE_TTL_SECONDS = 60


def _cache_key(
    provider_id: str, base_url: str | None, api_key_env: str | None
) -> tuple[str, str | None, str | None]:
    """Build a cache key from provider config."""
    return (provider_id, base_url, api_key_env)


def _get_cached_models(
    provider_id: str, base_url: str | None, api_key_env: str | None
) -> Any | None:
    """Retrieve cached models if still fresh."""
    key = _cache_key(provider_id, base_url, api_key_env)
    if key in _MODEL_CACHE:
        models, timestamp = _MODEL_CACHE[key]
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            return models
        else:
            del _MODEL_CACHE[key]
    return None


def _set_cached_models(
    provider_id: str, base_url: str | None, api_key_env: str | None, models: Any
) -> None:
    """Cache models with current timestamp."""
    key = _cache_key(provider_id, base_url, api_key_env)
    _MODEL_CACHE[key] = (models, time.time())


# Populated at module import time
_PROVIDERS: dict[str, ProviderAdapter] = {}


def _initialize_providers() -> None:
    """Populate the provider registry by importing provider modules."""
    from agentbox.core.providers import (
        anthropic,
        google,
        ollama,
        openai,
        openrouter,
        xai,
    )

    _PROVIDERS["openai"] = openai.OpenAIAdapter()
    _PROVIDERS["anthropic"] = anthropic.AnthropicAdapter()
    _PROVIDERS["google"] = google.GoogleAdapter()
    _PROVIDERS["openrouter"] = openrouter.OpenRouterAdapter()
    _PROVIDERS["xai"] = xai.XAIAdapter()
    _PROVIDERS["ollama"] = ollama.OllamaAdapter()


_initialize_providers()


def list_providers() -> list[ProviderDescriptor]:
    """List all registered provider descriptors."""
    return [adapter.descriptor for adapter in _PROVIDERS.values()]


def get_provider(provider_id: str) -> ProviderAdapter | None:
    """Get a provider adapter by ID, or None if not found."""
    return _PROVIDERS.get(provider_id)


async def list_models(
    provider_id: str, config: Any, refresh: bool = False
) -> list[Any]:
    """List models from a provider with short TTL cache.

    Args:
        provider_id: The provider ID (e.g., "openai", "ollama").
        config: EffectiveRunnerConfig with base_url and api_key_env.
        refresh: If True, bypass cache and fetch fresh models.

    Returns:
        List of ProviderModel objects.

    Raises:
        ValueError: If provider not found or config missing required fields.
        Exception: For HTTP errors (passed through).
    """
    adapter = get_provider(provider_id)
    if not adapter:
        raise ValueError(f"Provider not found: {provider_id}")

    base_url = config.base_url if config else None
    api_key_env = config.api_key_env if config else None

    if not refresh:
        cached = _get_cached_models(provider_id, base_url, api_key_env)
        if cached is not None:
            return cached

    models = await adapter.list_models(config)
    _set_cached_models(provider_id, base_url, api_key_env, models)
    return models
