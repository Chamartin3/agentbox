"""Runner provider API — list providers and discover available models.

Endpoints:
  GET /api/runner-providers                    — list provider descriptors
  GET /api/runner-providers/{provider_id}/models — list models for a provider

The models endpoint accepts optional configuration via query params:
  - profile_id: Load config from a stored runner profile
  - base_url: Override provider base URL
  - api_key_env: Environment variable name for API credentials
  - refresh: Force cache refresh (default: false)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from agentbox.api.deps import get_store
from agentbox.core.agent.profiles import EffectiveRunnerConfig
from agentbox.core.agent.providers import get_provider, list_providers
from agentbox.core.agent.providers.base import ProviderDescriptor, ProviderModel
from agentbox.core.agent.providers.registry import (
    list_models,
    refresh_opencode_providers,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runner-providers", tags=["runner-providers"])


@router.get("")
async def list_runner_providers(
    backend: str | None = Query(None),
) -> list[ProviderDescriptor]:
    """List provider descriptors, optionally filtered by backend compatibility.

    Args:
        backend: If set, return only providers whose ``compatible_backends``
            includes this backend id.
    """
    providers = list_providers()
    if backend is None:
        return providers
    return [p for p in providers if backend in (p.compatible_backends or [])]


@router.post("/refresh")
async def refresh_providers(backend: str | None = Query(None)) -> dict[str, Any]:
    """Re-run dynamic provider discovery and invalidate all model caches.

    Calls ``opencode models`` again — its output grows with available
    credentials — and clears the shared model-listing cache so the next
    ``/models`` call hits the live source for every provider.
    """
    from agentbox.core.agent.providers.registry import _MODEL_CACHE

    discovered = refresh_opencode_providers()
    _MODEL_CACHE.clear()
    return {
        "opencode": discovered,
        "opencode_count": len(discovered),
        "model_cache_cleared": True,
    }


@router.get("/{provider_id}/models")
async def list_provider_models(
    provider_id: str,
    profile_id: str | None = Query(None),
    base_url: str | None = Query(None),
    api_key_env: str | None = Query(None),
    backend: str | None = Query(None),
    refresh: bool = Query(False),
) -> list[ProviderModel]:
    """List available models from a provider.

    Configuration resolution (in order of preference):
      1. If profile_id given: load full config from stored runner profile
      2. Else: use query params (base_url, api_key_env)
      3. Fall back to provider descriptor defaults

    Args:
        provider_id: The provider ID (e.g., "openai", "openrouter").
        profile_id: Optional runner profile ID to use for config.
        base_url: Custom base URL for the provider (overrides defaults).
        api_key_env: Environment variable name for API credentials.
        refresh: If true, bypass cache and fetch fresh models.

    Returns:
        List of ProviderModel objects available from the provider.

    Raises:
        HTTPException 404: Provider not found.
        HTTPException 404: Runner profile not found (if profile_id given).
        HTTPException 400: Missing required configuration or invalid input.
        HTTPException 401/403: Authentication failed.
        HTTPException 502: Provider request failed.
    """
    # Step 1: Validate provider exists
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(404, {"error": f"Provider not found: {provider_id}"})

    # Step 1b: Validate backend compatibility (if specified)
    if backend is not None:
        compat = provider.descriptor.compatible_backends or []
        if backend not in compat:
            raise HTTPException(
                400,
                {
                    "error": (
                        f"provider {provider_id!r} is not compatible with "
                        f"backend {backend!r}"
                    )
                },
            )

    # Step 2: Build EffectiveRunnerConfig
    config: EffectiveRunnerConfig

    if profile_id:
        # Load from stored profile
        store = get_store()
        profile = store.get_runner_profile(profile_id)
        if not profile:
            raise HTTPException(404, {"error": f"Runner profile not found: {profile_id}"})

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
        # Use query params + descriptor defaults
        config = EffectiveRunnerConfig(
            backend=backend,
            base_url=base_url or provider.descriptor.default_base_url,
            api_key_env=api_key_env or provider.descriptor.default_api_key_env,
            provider=provider_id,
            source="run_override",
        )

    # Step 3: Call list_models
    try:
        models = await list_models(provider_id, config, refresh=refresh)
        return models
    except ValueError as e:
        # Missing API key env or other validation error
        logger.warning(f"Model listing validation error for {provider_id}: {e}")
        raise HTTPException(400, {"error": str(e)}) from e
    except httpx.HTTPStatusError as e:
        # Authentication errors
        if e.response.status_code in (401, 403):
            logger.warning(
                f"Authentication error from {provider_id}: {e.response.status_code}"
            )
            raise HTTPException(
                e.response.status_code,
                {"error": "Authentication failed"},
            ) from e
        # Other HTTP errors
        logger.error(f"HTTP error from {provider_id}: {e.response.status_code}")
        raise HTTPException(
            502,
            {"error": f"Provider request failed: {e.response.status_code}"},
        ) from e
    except httpx.RequestError as e:
        # Network, timeout, etc.
        logger.error(f"Request error from {provider_id}: {e}")
        raise HTTPException(
            502,
            {"error": "Provider request failed"},
        ) from e
    except Exception as e:
        # Unexpected error
        logger.exception(f"Unexpected error listing models from {provider_id}")
        raise HTTPException(
            502,
            {"error": "Provider request failed"},
        ) from e
