"""EngineService — the engines-domain public service object.

Owns all policy for runner profiles (CRUD, validation, system default,
agent binding) and exposes provider/backend passthroughs.

Stateful: the ``Database`` (managers) is resolved internally by ``Service``
from settings. Methods take only their domain arguments — never ``db`` or
``store``.

    svc = EngineService()
    svc.create_profile(RunnerProfileCreate(name="...", backend="claude_code"))

ponytail: provider/backend passthrough methods delegate to the registry,
not the DB. They remain here until a dedicated provider/backend service
emerges.
"""
from __future__ import annotations

import json as _json
import logging
import re
import uuid
from typing import Any

import httpx

from agentbox.core.agents import (
    engine_load_failure,
    list_engines,
    resolve_engine_by_name,
)
from agentbox.core.db import RunnerProfileManager
from agentbox.core.engines.backends import BackendAdapter
from agentbox.core.data import (
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfilePatch,
    RunnerProfileStats,
)
from agentbox.core.data.payload_types import RefreshProvidersResult
from agentbox.core.tools.registry import SharedToolRegistry, ToolSpec
from agentbox.core.data._util import now_iso
from agentbox.core.engines import (
    EffectiveRunnerConfig,
    ProviderDescriptor,
    ProviderModel,
    effective_backend,
    get_credential,
    get_provider,
    list_backends,
    list_credentials,
    list_models,
    list_models as registry_list_models,
    list_providers,
    refresh_opencode_providers,
)
from agentbox.core.engines.credentials import (
    CredentialMethod,
    CredentialState as CredentialState,
    Method as Method,
    load_all as _load_credentials,
)
from agentbox.core.engines.providers.registry import ProviderAdapter
from agentbox.core.service.base import Service
from agentbox.core.service.evaluation import EvaluationService

logger = logging.getLogger(__name__)

_load_credentials()  # registers credential methods (backends + providers)


def _slugify_id(name: str) -> str:
    """Derive a URL-safe profile id from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = "profile"
    return slug


def _derive_profile_id(name: str, existing_ids: set[str]) -> str:
    """Create a unique slug-style id from *name*, appending a numeric suffix on collision."""
    base = _slugify_id(name)
    if base not in existing_ids:
        return base
    for i in range(2, 1000):
        candidate = f"{base}-{i}"
        if candidate not in existing_ids:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:8]}"


class ProfileNotFound(LookupError):
    """A runner profile lookup by id returned nothing."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(f"runner profile not found: {profile_id!r}")
        self.profile_id = profile_id


class EngineService(Service):
    """Public API for the engines domain.

    Profile CRUD, agent bindings, system default, and provider/backend
    passthroughs all live here. Construction is zero-argument — ``Database``
    is resolved internally from settings.
    """

    def __init__(self) -> None:
        super().__init__()

    # ------------------------------------------------------------------
    # Profile CRUD
    # ------------------------------------------------------------------

    def list_profiles(
        self,
        backend: str | None = None,
        provider: str | None = None,
        enabled: bool | None = None,
    ) -> list[RunnerProfile]:
        """List runner profiles, optionally filtered."""
        rows = self._db.runner_profiles.list_all(
            backend=backend, provider=provider, enabled=enabled,
        )
        return list(rows)

    def create_profile(self, data: RunnerProfileCreate) -> RunnerProfile:
        """Create a new runner profile.

        Validates every field; derives an id from *name* when none is
        supplied; atomically clears ``is_system_default`` on sibling
        profiles when setting it True.
        """
        validate_create(data)

        if data.id:
            profile_id = data.id
        else:
            existing_ids = {p.id for p in self._db.runner_profiles.list_all()}
            profile_id = _derive_profile_id(data.name, existing_ids)

        now = now_iso()
        fields = {
            "id": profile_id,
            "name": data.name,
            "description": data.description,
            "backend": data.backend,
            "provider": data.provider,
            "model": data.model,
            "base_url": data.base_url,
            "api_key_env": data.api_key_env,
            "output_mode": data.output_mode,
            "params_json": _json.dumps(data.params),
            "headers_json": _json.dumps(data.headers),
            "extra_args_json": _json.dumps(data.extra_args),
            "is_enabled": int(data.is_enabled),
            "is_system_default": int(data.is_system_default),
            "created_at": now,
            "updated_at": now,
        }

        if data.is_system_default:
            row = self._db.runner_profiles.create_with_default_clear(**fields)
        else:
            row = self._db.runner_profiles.create_one(**fields)

        return row

    def get_profile(self, profile_id: str) -> RunnerProfile:
        """Return a single profile, raising ``ProfileNotFound`` if missing."""
        row = self._db.runner_profiles.get_by_id(profile_id)
        if row is None:
            raise ProfileNotFound(profile_id)
        return row

    def update_profile(
        self, profile_id: str, patch: RunnerProfilePatch
    ) -> RunnerProfile:
        """Partially update a runner profile.

        Validates the supplied fields; atomically clears
        ``is_system_default`` on sibling profiles when setting it True.
        """
        current = self.get_profile(profile_id)
        validate_patch(patch, current_backend=current.backend)

        values: dict[str, Any] = {}
        if patch.name is not None:
            values["name"] = patch.name
        if patch.description is not None:
            values["description"] = patch.description
        if patch.backend is not None:
            values["backend"] = patch.backend
        if patch.provider is not None:
            values["provider"] = patch.provider
        if patch.model is not None:
            values["model"] = patch.model
        if patch.base_url is not None:
            values["base_url"] = patch.base_url
        if patch.api_key_env is not None:
            values["api_key_env"] = patch.api_key_env
        if patch.output_mode is not None:
            values["output_mode"] = patch.output_mode
        if patch.params is not None:
            values["params_json"] = _json.dumps(patch.params)
        if patch.headers is not None:
            values["headers_json"] = _json.dumps(patch.headers)
        if patch.extra_args is not None:
            values["extra_args_json"] = _json.dumps(patch.extra_args)
        if patch.is_enabled is not None:
            values["is_enabled"] = int(patch.is_enabled)
        if patch.is_system_default is not None:
            values["is_system_default"] = int(patch.is_system_default)

        if not values:
            return current

        values["updated_at"] = now_iso()

        if values.get("is_system_default") == 1:
            row = self._db.runner_profiles.update_with_default_clear(
                profile_id, **values
            )
        else:
            row = self._db.runner_profiles.update_one(profile_id, **values)

        if row is None:
            raise ProfileNotFound(profile_id)
        return row

    def delete_profile(self, profile_id: str) -> None:
        """Delete a runner profile. Raises ``ProfileNotFound`` if missing."""
        if self._db.runner_profiles.get_by_id(profile_id) is None:
            raise ProfileNotFound(profile_id)
        self._db.runner_profiles.delete_one(profile_id)

    # ------------------------------------------------------------------
    # System default
    # ------------------------------------------------------------------

    def get_system_default_profile(self) -> RunnerProfile | None:
        """Return the system-default runner profile, or None."""
        row = self._db.runner_profiles.get_system_default()
        return row if row else None

    # ------------------------------------------------------------------
    # Agent ↔ profile binding
    # ------------------------------------------------------------------

    def get_agent_runner_profile(self, agent_id: str) -> RunnerProfile | None:
        """Return the profile bound to *agent_id*, or None."""
        row = self._db.runner_profiles.get_agent_profile(agent_id)
        return row if row else None

    def effective_backend(self, agent: Any) -> str:
        """The agent's effective backend — the single resolver's answer.

        A thin backend projection of ``RunnerProfileResolver.resolve()`` with
        no per-run overrides: agent-bound profile → system-default profile →
        ``the module-level default backend``. This is the one entry point every
        non-run caller (save validation, tool resolution, CLI dispatch,
        display, observability) uses to read "the agent's backend". It never
        consults the legacy ``runner.kind``.
        """
        return effective_backend(agent, self._db.runner_profiles)

    def set_agent_runner_profile(
        self, agent_id: str, profile_id: str
    ) -> RunnerProfile:
        """Bind a runner profile to an agent (idempotent upsert).

        Returns the full profile data for the bound profile id.
        """
        # Validate first: the binding column is an enforced FK now, so a missing
        # profile would raise IntegrityError on insert. get_profile raises the
        # 404-mapped ProfileNotFound instead.
        profile = self.get_profile(profile_id)
        now = now_iso()
        self._db.runner_profiles.set_agent_profile(
            agent_id, profile_id, created_at=now, updated_at=now,
        )
        return profile

    def clear_agent_runner_profile(self, agent_id: str) -> None:
        """Remove the profile binding for *agent_id*."""
        self._db.runner_profiles.clear_agent_profile(agent_id)

    # ------------------------------------------------------------------
    # Profile stats (delegates to EvaluationService)
    # ------------------------------------------------------------------

    def get_profile_stats(
        self,
        profile_id: str,
        since: str | None = None,
        until: str | None = None,
    ) -> RunnerProfileStats:
        """Aggregate stats for a single runner profile.

        Raises ``ProfileNotFound`` if the profile does not exist.
        """
        if self._db.runner_profiles.get_by_id(profile_id) is None:
            raise ProfileNotFound(profile_id)
        return EvaluationService().runner_profile_stats(profile_id, since=since, until=until)

    def list_profile_stats(
        self,
        since: str | None = None,
        until: str | None = None,
    ) -> list[RunnerProfileStats]:
        """Aggregate stats for all runner profiles."""
        return EvaluationService().list_runner_profile_stats(since=since, until=until)

    # ------------------------------------------------------------------
    # Provider / backend passthrough
    # ------------------------------------------------------------------

    def list_runner_providers(
        self, backend: str | None = None
    ) -> list[ProviderDescriptor]:
        """List available runner providers, optionally filtered by backend."""
        providers = list_providers()
        if backend is None:
            return providers
        return [p for p in providers if backend in (p.compatible_backends or [])]

    def get_runner_provider(self, provider_id: str) -> ProviderAdapter | None:
        """Return the provider adapter for *provider_id*, or ``None``."""
        return get_provider(provider_id)

    async def list_provider_models(
        self,
        provider_id: str,
        profile_id: str | None = None,
        base_url: str | None = None,
        api_key_env: str | None = None,
        backend: str | None = None,
        refresh: bool = False,
    ) -> list[ProviderModel]:
        """Resolve config and list models for a provider.

        ponytail: delegates to the module-level ``list_provider_models``
        while a dedicated providers service is not yet extracted.
        """
        return await list_provider_models(
            provider_id,
            runner_profiles=self._db.runner_profiles,
            profile_id=profile_id,
            base_url=base_url,
            api_key_env=api_key_env,
            backend=backend,
            refresh=refresh,
        )

    def backends(self) -> dict[str, type[BackendAdapter]]:
        """Return all registered backends (engine registry)."""
        return list_engines()

    def get_backend(self, name: str) -> type[BackendAdapter]:
        """Resolve a backend by name."""
        return resolve_engine_by_name(name)

    def list_backend_names(self) -> list[str]:
        """Sorted names of registered backend adapters."""
        return list_backends()

    # ── Providers (registry passthrough) ──────────────────────────────
    def list_providers(self) -> list[ProviderDescriptor]:
        """All runner provider descriptors."""
        return list_providers()

    def get_provider(self, provider_id: str) -> ProviderAdapter | None:
        """Return the provider adapter for *provider_id*, or ``None``."""
        return get_provider(provider_id)

    async def list_provider_models_raw(
        self, provider_id: str, config: Any, refresh: bool = False
    ) -> list[ProviderModel]:
        """List a provider's models via the registry with a resolved config."""
        return await list_models(provider_id, config, refresh=refresh)

    def refresh_opencode_providers(self) -> list[str]:
        """Re-discover opencode providers; returns the discovered descriptors."""
        return refresh_opencode_providers()

    # ── Credentials (registry passthrough) ────────────────────────────
    def list_credentials(self) -> list[CredentialMethod]:
        """All registered credential methods with resolved state."""
        return list_credentials()

    def get_credential(self, name: str) -> CredentialMethod | None:
        """Resolve a single credential method by name, or ``None``."""
        return get_credential(name)

    # ── Shared tool registry passthrough ──────────────────────────────
    def list_shared_tools(self) -> list[ToolSpec]:
        """All consumer-registered shared agent tools discovered at startup.

        Read-only passthrough to ``SharedToolRegistry.all()``. MCP tool
        bodies call this via ``ctx.engines.list_shared_tools()`` rather
        than importing the in-process registry directly.
        """
        return SharedToolRegistry.all()


# ══════════════════════════════════════════════════════════════════════════
# Runner-profile field validators (merged from profile_validation.py).
# Kept module-level so the ``core.agents`` / ``core.engines`` names they call
# stay monkeypatchable at ``agentbox.core.service.engines.<name>``.
# ══════════════════════════════════════════════════════════════════════════


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


# ══════════════════════════════════════════════════════════════════════════
# Provider discovery + model listing (merged from providers.py).
# ══════════════════════════════════════════════════════════════════════════


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


def list_runner_providers(*, backend: str | None = None) -> list[ProviderDescriptor]:
    providers = list_providers()
    if backend is None:
        return providers
    return [p for p in providers if backend in (p.compatible_backends or [])]


def refresh_providers() -> RefreshProvidersResult:
    """Re-run dynamic provider discovery and invalidate model caches."""
    discovered = refresh_opencode_providers()
    # refresh_opencode_providers() already clears _MODEL_CACHE internally.
    return {
        "opencode": discovered,
        "opencode_count": len(discovered),
        "model_cache_cleared": True,
    }


async def list_provider_models(
    provider_id: str,
    *,
    runner_profiles: RunnerProfileManager,
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
        row = runner_profiles.get_by_id(profile_id)
        if not row:
            raise InvalidProviderRequest(f"Runner profile not found: {profile_id}")
        profile = row
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
