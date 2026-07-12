"""Runner provider API — list providers and discover available models.

Transport-only: parses query params, calls
:mod:`agentbox.core.service.engines`, maps domain errors to HTTP.

Endpoints:
  GET /api/runner-providers                    — list provider descriptors
  POST /api/runner-providers/refresh           — refresh dynamic discovery
  GET /api/runner-providers/{provider_id}/models — list models for a provider
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from agentbox.api.deps import get_db
from agentbox.core.data.payload_types import RefreshProvidersResult
import agentbox.core.service.engines as svc
from agentbox.core.service.engines import ProviderDescriptor, ProviderModel
from agentbox.core.service.engines import (
    InvalidProviderRequest,
    ProviderAuthFailed,
    ProviderNotFound,
    ProviderUpstreamError,
)

router = APIRouter(prefix="/api/runner-providers", tags=["runner-providers"])


@router.get("")
async def list_runner_providers(
    backend: str | None = Query(None),
) -> list[ProviderDescriptor]:
    """List provider descriptors, optionally filtered by backend compatibility."""
    return svc.list_runner_providers(backend=backend)


@router.post("/refresh")
async def refresh_providers(backend: str | None = Query(None)) -> RefreshProvidersResult:
    """Re-run dynamic provider discovery and invalidate all model caches."""
    return svc.refresh_providers()


@router.get("/{provider_id}/models")
async def list_provider_models(
    provider_id: str,
    profile_id: str | None = Query(None),
    base_url: str | None = Query(None),
    api_key_env: str | None = Query(None),
    backend: str | None = Query(None),
    refresh: bool = Query(False),
) -> list[ProviderModel]:
    """List available models from a provider."""
    try:
        db = get_db()
        return await svc.list_provider_models(
            provider_id,
            runner_profiles=db.runner_profiles,
            profile_id=profile_id,
            base_url=base_url,
            api_key_env=api_key_env,
            backend=backend,
            refresh=refresh,
        )
    except ProviderNotFound as exc:
        raise HTTPException(404, {"error": str(exc)}) from exc
    except InvalidProviderRequest as exc:
        # Profile-not-found path used to return 404; keep that behavior.
        msg = str(exc)
        status = 404 if msg.startswith("Runner profile not found") else 400
        raise HTTPException(status, {"error": msg}) from exc
    except ProviderAuthFailed as exc:
        raise HTTPException(exc.status_code, {"error": "Authentication failed"}) from exc
    except ProviderUpstreamError as exc:
        raise HTTPException(502, {"error": str(exc)}) from exc
