"""/runner-profiles endpoints — CRUD, agent binding, stats."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response

from agentbox.api._pagination import paginate_list
from agentbox.api.deps import get_store
from agentbox.core.data import SessionStore
from agentbox.core.data.runner_profiles import (
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfilePatch,
    RunnerProfileStats,
)
from agentbox.core.plugins import get_backend
from agentbox.core.providers import get_provider, list_providers

router = APIRouter(prefix="/api/runner-profiles", tags=["runner-profiles"])



def _validate_backend(backend: str) -> None:
    """Validate backend is registered. Raises HTTPException 400 if invalid."""
    try:
        get_backend(backend)
    except KeyError as exc:
        raise HTTPException(400, f"unknown backend: {backend!r}") from exc


def _validate_provider(provider: str | None) -> None:
    """Validate provider is registered. Raises HTTPException 400 if invalid."""
    if provider is None:
        return
    provider_ids = {p.id for p in list_providers()}
    if provider not in provider_ids:
        raise HTTPException(400, f"unknown provider: {provider!r}")


def _validate_timeout_seconds(timeout_seconds: int | None) -> None:
    """Validate timeout_seconds is positive. Raises HTTPException 400 if invalid."""
    if timeout_seconds is None:
        return
    if timeout_seconds <= 0:
        raise HTTPException(400, "timeout_seconds must be positive")


def _validate_base_url(base_url: str | None) -> None:
    """Validate base_url starts with http:// or https://. Raises HTTPException 400 if invalid."""
    if base_url is None:
        return
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise HTTPException(400, "base_url must start with http:// or https://")


def _validate_api_key_env(api_key_env: str | None) -> None:
    """Validate api_key_env looks like an env var name, not a secret.
    Raises HTTPException 400 if invalid or suspicious.
    """
    if api_key_env is None:
        return

    # Check if looks like a secret value
    if api_key_env.startswith("sk-") or api_key_env.startswith("Bearer "):
        raise HTTPException(
            400,
            "api_key_env looks like a secret value, not an env var name",
        )
    if len(api_key_env) > 64:
        raise HTTPException(
            400,
            "api_key_env looks like a secret value, not an env var name",
        )

    # Check env var name format: ^[A-Z][A-Z0-9_]*$
    if not re.match(r"^[A-Z][A-Z0-9_]*$", api_key_env):
        raise HTTPException(
            400,
            "api_key_env must be a valid env var name (uppercase letters, digits, underscores)",
        )


def _validate_backend_provider_compat(
    backend: str, provider: str | None
) -> None:
    """Reject (backend, provider) pairs that the provider doesn't declare.

    Skipped when provider is None (no provider is always valid — backends
    like claude_code can run on the host's own OAuth credentials).
    """
    if provider is None:
        return
    adapter = get_provider(provider)
    if adapter is None:
        return  # _validate_provider will catch this separately
    compatible = adapter.descriptor.compatible_backends or []
    if backend not in compatible:
        raise HTTPException(
            400,
            (
                f"provider {provider!r} is not compatible with backend "
                f"{backend!r} (compatible: {', '.join(compatible) or 'none'})"
            ),
        )


def _validate_headers(headers: dict[str, str] | None) -> None:
    """Validate headers don't include Authorization. Raises HTTPException 400 if invalid."""
    if headers is None:
        return
    for key in headers:
        if key.lower() == "authorization":
            raise HTTPException(400, "headers cannot include Authorization")


def _validate_create_body(data: RunnerProfileCreate) -> None:
    """Validate all fields in a RunnerProfileCreate."""
    _validate_backend(data.backend)
    _validate_provider(data.provider)
    _validate_backend_provider_compat(data.backend, data.provider)
    _validate_timeout_seconds(data.timeout_seconds)
    _validate_base_url(data.base_url)
    _validate_api_key_env(data.api_key_env)
    _validate_headers(data.headers)


def _validate_patch_body(
    patch: RunnerProfilePatch, current_backend: str
) -> None:
    """Validate all fields in a RunnerProfilePatch.

    ``current_backend`` is the profile's existing backend, used to enforce
    backend↔provider compatibility when only one of the two is being
    patched (the other side is implied by the current row).
    """
    if patch.backend is not None:
        _validate_backend(patch.backend)
    if patch.provider is not None:
        _validate_provider(patch.provider)
    effective_backend = patch.backend or current_backend
    if patch.provider is not None or patch.backend is not None:
        _validate_backend_provider_compat(effective_backend, patch.provider)
    _validate_timeout_seconds(patch.timeout_seconds)
    _validate_base_url(patch.base_url)
    _validate_api_key_env(patch.api_key_env)
    _validate_headers(patch.headers)


@router.get("")
def list_runner_profiles(
    response: Response,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str = "asc",
    limit: int = 50,
    offset: int = 0,
    paginated: bool = False,
    store: SessionStore = Depends(get_store),
) -> list[RunnerProfile] | dict:
    """List runner profiles with optional filters.

    Pass ``paginated=true`` (or any of ``q/sort/order/offset``) to get the
    envelope ``{items, total, offset, limit, has_more}``. Otherwise returns
    a plain list for backward compatibility.
    """
    profiles = store.list_runner_profiles(
        backend=backend, provider=provider, enabled=enabled
    )

    if not paginated and not any([q, sort, offset]):
        return profiles

    items_as_dicts = [p.model_dump() for p in profiles]
    page = paginate_list(
        items_as_dicts,
        q=q,
        q_fields=("id", "name", "backend", "provider", "model"),
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(page["total"])
    return page


@router.post("", status_code=201)
def create_runner_profile(
    data: RunnerProfileCreate,
    store: SessionStore = Depends(get_store),
) -> RunnerProfile:
    """Create a new runner profile."""
    _validate_create_body(data)
    return store.create_runner_profile(data)


@router.get("/{profile_id}")
def get_runner_profile(
    profile_id: str,
    store: SessionStore = Depends(get_store),
) -> RunnerProfile:
    """Get a runner profile by ID."""
    profile = store.get_runner_profile(profile_id)
    if profile is None:
        raise HTTPException(404, f"runner profile not found: {profile_id!r}")
    return profile


@router.patch("/{profile_id}")
def update_runner_profile(
    profile_id: str,
    patch: RunnerProfilePatch,
    store: SessionStore = Depends(get_store),
) -> RunnerProfile:
    """Update a runner profile."""
    # Check profile exists
    current = store.get_runner_profile(profile_id)
    if current is None:
        raise HTTPException(404, f"runner profile not found: {profile_id!r}")

    _validate_patch_body(patch, current_backend=current.backend)
    return store.update_runner_profile(profile_id, patch)


@router.delete("/{profile_id}")
def delete_runner_profile(
    profile_id: str,
    store: SessionStore = Depends(get_store),
) -> None:
    """Delete a runner profile."""
    if store.get_runner_profile(profile_id) is None:
        raise HTTPException(404, f"runner profile not found: {profile_id!r}")
    store.delete_runner_profile(profile_id)


@router.get("/{profile_id}/stats")
def get_runner_profile_stats(
    profile_id: str,
    since: str | None = None,
    until: str | None = None,
    store: SessionStore = Depends(get_store),
) -> RunnerProfileStats:
    """Get statistics for a runner profile."""
    if store.get_runner_profile(profile_id) is None:
        raise HTTPException(404, f"runner profile not found: {profile_id!r}")
    return store.runner_profile_stats(profile_id, since=since, until=until)


