"""Service layer for runner-provider discovery and model listing.

Resolves a provider's :class:`EffectiveRunnerConfig` from either a stored
runner profile or query-style overrides, then delegates to the cached
``list_models`` registry. Translates upstream HTTP errors into domain
errors so the transport layer can map them uniformly.

Domain errors raised here:

* :class:`ProviderNotFound` — unknown provider id.
* :class:`InvalidProviderRequest` — bad backend↔provider pair, missing
  api key, or other validation issue.
* :class:`ProviderAuthFailed` — upstream 401/403.
* :class:`ProviderUpstreamError` — any other upstream failure (5xx,
  network, etc.).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from agentbox.core.agent.profiles import EffectiveRunnerConfig
from agentbox.core.agent.providers import get_provider, list_providers
from agentbox.core.agent.providers.base import ProviderDescriptor, ProviderModel
from agentbox.core.agent.providers.registry import (
    list_models as registry_list_models,
)
from agentbox.core.agent.providers.registry import (
    refresh_opencode_providers,
)

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore

logger = logging.getLogger(__name__)

__all__ = [
    "ProviderNotFound",
    "InvalidProviderRequest",
    "ProviderAuthFailed",
    "ProviderUpstreamError",
    "list_runner_providers",
    "refresh_providers",
    "list_provider_models",
]


class ProviderNotFound(LookupError):
    def __init__(self, provider_id: str) -> None:
        super().__init__(f"Provider not found: {provider_id}")
        self.provider_id = provider_id


class InvalidProviderRequest(ValueError):
    """Validation rejection for a model-listing request."""


class ProviderAuthFailed(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__("Authentication failed")
        self.status_code = status_code


class ProviderUpstreamError(RuntimeError):
    """Catch-all for non-auth upstream provider failures."""


def list_runner_providers(
    *, backend: str | None = None
) -> list[ProviderDescriptor]:
    providers = list_providers()
    if backend is None:
        return providers
    return [p for p in providers if backend in (p.compatible_backends or [])]


def refresh_providers() -> dict[str, Any]:
    """Re-run dynamic provider discovery and invalidate model caches."""
    from agentbox.core.agent.providers.registry import _MODEL_CACHE

    discovered = refresh_opencode_providers()
    _MODEL_CACHE.clear()
    return {
        "opencode": discovered,
        "opencode_count": len(discovered),
        "model_cache_cleared": True,
    }


async def list_provider_models(
    provider_id: str,
    *,
    store: SessionStore,
    profile_id: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    backend: str | None = None,
    refresh: bool = False,
) -> list[ProviderModel]:
    """Resolve config and list models for a provider.

    Raises:
        ProviderNotFound: provider id is unknown.
        InvalidProviderRequest: profile id missing, incompatible backend,
            or upstream validation rejection.
        ProviderAuthFailed: upstream 401/403.
        ProviderUpstreamError: other upstream failure.
    """
    provider = get_provider(provider_id)
    if not provider:
        raise ProviderNotFound(provider_id)

    if backend is not None:
        compat = provider.descriptor.compatible_backends or []
        if backend not in compat:
            raise InvalidProviderRequest(
                f"provider {provider_id!r} is not compatible with backend "
                f"{backend!r}"
            )

    config: EffectiveRunnerConfig
    if profile_id:
        profile = store.get_runner_profile(profile_id)
        if not profile:
            raise InvalidProviderRequest(f"Runner profile not found: {profile_id}")
        config = EffectiveRunnerConfig(
            backend=profile.backend,
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key_env=profile.api_key_env,
            params=profile.params or {},
            headers=profile.headers or {},
            extra_args=profile.extra_args or [],
            profile_id=profile.id,
            source="run_profile",
        )
    else:
        config = EffectiveRunnerConfig(
            backend=backend,
            base_url=base_url or provider.descriptor.default_base_url,
            api_key_env=api_key_env or provider.descriptor.default_api_key_env,
            provider=provider_id,
            source="run_override",
        )

    try:
        return await registry_list_models(provider_id, config, refresh=refresh)
    except ValueError as exc:
        logger.warning(f"Model listing validation error for {provider_id}: {exc}")
        raise InvalidProviderRequest(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            logger.warning(
                f"Authentication error from {provider_id}: {exc.response.status_code}"
            )
            raise ProviderAuthFailed(exc.response.status_code) from exc
        logger.error(f"HTTP error from {provider_id}: {exc.response.status_code}")
        raise ProviderUpstreamError(
            f"Provider request failed: {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        logger.error(f"Request error from {provider_id}: {exc}")
        raise ProviderUpstreamError("Provider request failed") from exc
    except Exception as exc:
        logger.exception(f"Unexpected error listing models from {provider_id}")
        raise ProviderUpstreamError("Provider request failed") from exc
