"""Service layer for runner-profile CRUD + validation.

Moves the per-field validators (backend, provider, base_url,
api_key_env, headers, backend↔provider compatibility) out of the
REST route so MCP / CLI surfaces can reuse them.

Domain errors raised here:

* :class:`InvalidProfile` — validation rejection (bad backend,
  unknown provider, malformed api_key_env, etc.).
* :class:`ProfileNotFound` — lookup miss for an existing profile id.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from agentbox.core.agent.plugins import backend_load_failure, backends, get_backend
from agentbox.core.agent.providers import get_provider, list_providers

if TYPE_CHECKING:
    from agentbox.core.data import (RunnerProfile,
        RunnerProfileCreate,
        RunnerProfilePatch,
        RunnerProfileStats,
    )
    from agentbox.core.data import SessionStore

__all__ = [
    "InvalidProfile",
    "ProfileNotFound",
    "validate_create",
    "validate_patch",
    "list_profiles",
    "create_profile",
    "get_profile",
    "update_profile",
    "delete_profile",
    "get_profile_stats",
    "list_runner_profiles",
    "get_runner_profile",
    "create_runner_profile",
    "delete_runner_profile",
    "set_agent_runner_profile",
    "get_agent_runner_profile",
    "runner_profile_stats",
    "list_runner_profile_stats",
]


class InvalidProfile(ValueError):
    """Validation rejection for a runner-profile field."""


class ProfileNotFound(LookupError):
    def __init__(self, profile_id: str) -> None:
        super().__init__(f"runner profile not found: {profile_id!r}")
        self.profile_id = profile_id


# ---------------------------------------------------------------------------
# Per-field validators
# ---------------------------------------------------------------------------


def _validate_backend(backend: str) -> None:
    """Validate ``backend`` resolves in the live plugin registry.

    Distinguishes two failure modes so the caller knows whether the value
    is wrong (typo / removed plugin) or the *server* is misconfigured
    (entry point declared but module failed to import — usually a missing
    Python dep). Without this split, both cases collapse to "unknown
    backend" and the operator can't tell them apart.
    """
    try:
        get_backend(backend)
    except KeyError as exc:
        failure = backend_load_failure(backend)
        if failure is not None:
            raise InvalidProfile(
                f"backend {backend!r} is declared but failed to load at startup "
                f"({failure}). Fix the agentbox install before binding it."
            ) from exc
        raise InvalidProfile(
            f"unknown backend: {backend!r}. Registered: {sorted(backends().keys())}."
        ) from exc


def _validate_provider(provider: str | None) -> None:
    if provider is None:
        return
    provider_ids = {p.id for p in list_providers()}
    if provider not in provider_ids:
        raise InvalidProfile(f"unknown provider: {provider!r}")


def _validate_base_url(base_url: str | None) -> None:
    if base_url is None:
        return
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise InvalidProfile("base_url must start with http:// or https://")


def _validate_api_key_env(api_key_env: str | None) -> None:
    if api_key_env is None:
        return
    if api_key_env.startswith("sk-") or api_key_env.startswith("Bearer "):
        raise InvalidProfile(
            "api_key_env looks like a secret value, not an env var name"
        )
    if len(api_key_env) > 64:
        raise InvalidProfile(
            "api_key_env looks like a secret value, not an env var name"
        )
    if not re.match(r"^[A-Z][A-Z0-9_]*$", api_key_env):
        raise InvalidProfile(
            "api_key_env must be a valid env var name "
            "(uppercase letters, digits, underscores)"
        )


def _validate_backend_provider_compat(backend: str, provider: str | None) -> None:
    """Reject (backend, provider) pairs that the provider doesn't declare.

    Skipped when provider is None (no provider is always valid — backends
    like claude_code can run on the host's own OAuth credentials).
    """
    if provider is None:
        return
    adapter = get_provider(provider)
    if adapter is None:
        return  # _validate_provider catches this separately
    compatible = adapter.descriptor.compatible_backends or []
    if backend not in compatible:
        raise InvalidProfile(
            f"provider {provider!r} is not compatible with backend "
            f"{backend!r} (compatible: {', '.join(compatible) or 'none'})"
        )


def _validate_headers(headers: dict[str, str] | None) -> None:
    if headers is None:
        return
    for key in headers:
        if key.lower() == "authorization":
            raise InvalidProfile("headers cannot include Authorization")


def validate_create(data: RunnerProfileCreate) -> None:
    _validate_backend(data.backend)
    _validate_provider(data.provider)
    _validate_backend_provider_compat(data.backend, data.provider)
    _validate_base_url(data.base_url)
    _validate_api_key_env(data.api_key_env)
    _validate_headers(data.headers)


def validate_patch(patch: RunnerProfilePatch, current_backend: str) -> None:
    """Validate a patch given the profile's existing backend.

    ``current_backend`` is used to enforce backend↔provider compatibility
    when only one of the two is being patched (the other side is implied
    by the current row).
    """
    if patch.backend is not None:
        _validate_backend(patch.backend)
    if patch.provider is not None:
        _validate_provider(patch.provider)
    effective_backend = patch.backend or current_backend
    if patch.provider is not None or patch.backend is not None:
        _validate_backend_provider_compat(effective_backend, patch.provider)
    _validate_base_url(patch.base_url)
    _validate_api_key_env(patch.api_key_env)
    _validate_headers(patch.headers)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_profiles(
    *,
    store: SessionStore,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
) -> list[RunnerProfile]:
    return store.list_runner_profiles(backend=backend, provider=provider, enabled=enabled)


def create_profile(
    data: RunnerProfileCreate, *, store: SessionStore
) -> RunnerProfile:
    validate_create(data)
    return store.create_runner_profile(data)


def get_profile(profile_id: str, *, store: SessionStore) -> RunnerProfile:
    profile = store.get_runner_profile(profile_id)
    if profile is None:
        raise ProfileNotFound(profile_id)
    return profile


def update_profile(
    profile_id: str, patch: RunnerProfilePatch, *, store: SessionStore
) -> RunnerProfile:
    current = store.get_runner_profile(profile_id)
    if current is None:
        raise ProfileNotFound(profile_id)
    validate_patch(patch, current_backend=current.backend)
    return store.update_runner_profile(profile_id, patch)


def delete_profile(profile_id: str, *, store: SessionStore) -> None:
    if store.get_runner_profile(profile_id) is None:
        raise ProfileNotFound(profile_id)
    store.delete_runner_profile(profile_id)


def get_profile_stats(
    profile_id: str,
    *,
    store: SessionStore,
    since: str | None = None,
    until: str | None = None,
) -> RunnerProfileStats:
    if store.get_runner_profile(profile_id) is None:
        raise ProfileNotFound(profile_id)
    return store.runner_profile_stats(profile_id, since=since, until=until)


# ---------------------------------------------------------------------------
# Pass-through wrappers for CLI consumers
# ---------------------------------------------------------------------------


def list_runner_profiles(
    store: SessionStore,
    *,
    backend: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
) -> list[RunnerProfile]:
    return store.list_runner_profiles(backend=backend, provider=provider, enabled=enabled)


def get_runner_profile(store: SessionStore, profile_id: str) -> RunnerProfile | None:
    return store.get_runner_profile(profile_id)


def create_runner_profile(
    store: SessionStore, profile: RunnerProfileCreate
) -> RunnerProfile:
    return store.create_runner_profile(profile)


def delete_runner_profile(store: SessionStore, profile_id: str) -> None:
    store.delete_runner_profile(profile_id)


def set_agent_runner_profile(
    store: SessionStore, agent_id: str, profile_id: str
) -> RunnerProfile:
    return store.set_agent_runner_profile(agent_id, profile_id)


def get_agent_runner_profile(
    store: SessionStore, agent_id: str
) -> RunnerProfile | None:
    return store.get_agent_runner_profile(agent_id)


def runner_profile_stats(
    store: SessionStore,
    profile_id: str,
    *,
    since: str | None = None,
    until: str | None = None,
) -> RunnerProfileStats:
    return store.runner_profile_stats(profile_id, since=since, until=until)


def list_runner_profile_stats(
    store: SessionStore,
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[RunnerProfileStats]:
    return store.list_runner_profile_stats(since=since, until=until)
