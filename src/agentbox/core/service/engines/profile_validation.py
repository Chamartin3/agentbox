"""Per-field validators for runner profiles.

Public surface for CRUD callers (``service.engines.profiles``) and any
adapter that wants to validate a ``RunnerProfileCreate`` /
``RunnerProfilePatch`` payload before persisting it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from agentbox.core.agents.resolve import (
    engine_load_failure,
    list_engines,
    resolve_engine_by_name,
)
from agentbox.core.engines.providers import get_provider, list_providers

if TYPE_CHECKING:
    from agentbox.core.data import RunnerProfileCreate, RunnerProfilePatch


class InvalidProfile(ValueError):
    """Validation rejection for a runner-profile field."""


def _validate_backend(backend: str) -> None:
    try:
        resolve_engine_by_name(backend)
    except KeyError as exc:
        failure = engine_load_failure(backend)
        if failure is not None:
            raise InvalidProfile(
                f"backend {backend!r} is declared but failed to load at startup "
                f"({failure}). Fix the agentbox install before binding it."
            ) from exc
        raise InvalidProfile(
            f"unknown backend: {backend!r}. Registered: {sorted(list_engines().keys())}."
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
    if provider is None:
        return
    adapter = get_provider(provider)
    if adapter is None:
        return
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


__all__ = [
    "InvalidProfile",
    "validate_create",
    "validate_patch",
]
