"""Provider registry with model listing cache."""

import logging
import time
from typing import Any

from agentbox.core.data.constants import BackendName
import agentbox.core.engines.providers.anthropic as anthropic
import agentbox.core.engines.providers.cli as cli
import agentbox.core.engines.providers.deepseek as deepseek
import agentbox.core.engines.providers.google as google
import agentbox.core.engines.providers.ollama as ollama
import agentbox.core.engines.providers.openai as openai
import agentbox.core.engines.providers.openrouter as openrouter
import agentbox.core.engines.providers.xai as xai
from agentbox.core.engines.providers.base import ProviderAdapter, ProviderDescriptor, ProviderModel

logger = logging.getLogger(__name__)

# Module-level cache: (provider_id, base_url, api_key_env, backend) -> (models, timestamp)
_MODEL_CACHE: dict[
    tuple[str, str | None, str | None, str | None], tuple[Any, float]
] = {}
_CACHE_TTL_SECONDS = 3600  # 1-hour cache — cold-load pages have data without a live round-trip


def _cache_key(
    provider_id: str,
    base_url: str | None,
    api_key_env: str | None,
    backend: str | None,
) -> tuple[str, str | None, str | None, str | None]:
    """Build a cache key from provider config."""
    return (provider_id, base_url, api_key_env, backend)


def _get_cached_models(
    provider_id: str,
    base_url: str | None,
    api_key_env: str | None,
    backend: str | None,
) -> Any | None:
    """Retrieve cached models if still fresh."""
    key = _cache_key(provider_id, base_url, api_key_env, backend)
    if key in _MODEL_CACHE:
        models, timestamp = _MODEL_CACHE[key]
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            return models
        else:
            del _MODEL_CACHE[key]
    return None


def _set_cached_models(
    provider_id: str,
    base_url: str | None,
    api_key_env: str | None,
    backend: str | None,
    models: Any,
) -> None:
    """Cache models with current timestamp."""
    key = _cache_key(provider_id, base_url, api_key_env, backend)
    _MODEL_CACHE[key] = (models, time.time())


# Populated at module import time
_PROVIDERS: dict[str, ProviderAdapter] = {}


def _initialize_providers() -> None:
    """Populate the provider registry by importing provider modules."""
    _PROVIDERS["openai"] = openai.OpenAIAdapter()
    _PROVIDERS["anthropic"] = anthropic.AnthropicAdapter()
    _PROVIDERS["google"] = google.GoogleAdapter()
    _PROVIDERS["openrouter"] = openrouter.OpenRouterAdapter()
    _PROVIDERS["xai"] = xai.XAIAdapter()
    _PROVIDERS["deepseek"] = deepseek.DeepSeekAdapter()
    _PROVIDERS["ollama"] = ollama.OllamaAdapter()
    _PROVIDERS[BackendName.CODEX] = cli.CodexCLIAdapter()


def refresh_opencode_providers() -> list[str]:
    """Re-discover OpenCode CLI provider prefixes and update the registry.

    Returns the sorted list of provider ids now registered for the
    opencode backend. The set grows as credentials become available
    inside the container (env vars or ``opencode providers login``).
    """
    discovered = cli.discover_opencode_providers()

    # Drop any existing opencode-backed adapters that came from a previous
    # discovery pass; HTTP/static providers (openai, ollama, ...) are left
    # alone even though some of them are listed by ``opencode models``.
    for pid in list(_PROVIDERS):
        adapter = _PROVIDERS[pid]
        if isinstance(adapter, cli.OpenCodeCLIAdapter):
            del _PROVIDERS[pid]

    for prefix in discovered:
        existing = _PROVIDERS.get(prefix)
        if existing is not None:
            compat = list(existing.descriptor.compatible_backends or [])
            if BackendName.OPENCODE not in compat:
                # A first-class (HTTP/token) adapter already owns this prefix
                # (e.g. ``openai``, ``deepseek``). opencode drives the *same*
                # provider, so mark that existing provider opencode-compatible
                # rather than cloning a confusing ``opencode-<prefix>`` sibling.
                # model_copy shadows the (ClassVar) descriptor on this instance
                # only, keeping the adapter class pristine for fresh instances.
                # setattr: shadow the ClassVar descriptor on this instance only
                # (the ProviderAdapter protocol types ``descriptor`` read-only).
                setattr(
                    existing,
                    "descriptor",
                    existing.descriptor.model_copy(
                        update={"compatible_backends": [*compat, BackendName.OPENCODE]}
                    ),
                )
            continue
        # No first-class adapter owns this prefix — register the opencode view.
        _PROVIDERS[prefix] = cli.OpenCodeCLIAdapter(
            cli_prefix=prefix,
            descriptor_id=prefix,
        )

    # Invalidate any cached model listings — provider set just changed.
    _MODEL_CACHE.clear()

    if discovered:
        logger.info("opencode provider discovery: %s", ", ".join(discovered))
    else:
        logger.debug(
            "opencode provider discovery returned no providers "
            "(binary missing or call failed)"
        )
    return discovered


_initialize_providers()
try:
    refresh_opencode_providers()
except Exception:  # discovery is best-effort at import time
    logger.exception("initial opencode provider discovery failed")


def list_providers() -> list[ProviderDescriptor]:
    """List all registered provider descriptors."""
    return [adapter.descriptor for adapter in _PROVIDERS.values()]


def get_provider(provider_id: str) -> ProviderAdapter | None:
    """Get a provider adapter by ID, or None if not found."""
    return _PROVIDERS.get(provider_id)


async def list_models(
    provider_id: str, config: Any, refresh: bool = False
) -> list[ProviderModel]:
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
    backend = config.backend if config else None

    if not refresh:
        cached = _get_cached_models(provider_id, base_url, api_key_env, backend)
        if cached is not None:
            return cached

    models = await adapter.list_models(config)
    _set_cached_models(provider_id, base_url, api_key_env, backend, models)
    return models
