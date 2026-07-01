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
import re
import uuid
from typing import Any

from agentbox.core.agents.resolve import list_engines, resolve_engine_by_name
from agentbox.core.data import (
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfilePatch,
    RunnerProfileStats,
)
from agentbox.core.tools.registry import SharedToolRegistry, ToolSpec
from agentbox.core.data._util import now_iso
from agentbox.core.engines import (
    ProviderDescriptor,
    ProviderModel,
    get_credential,
    get_provider,
    list_backends,
    list_credentials,
    list_models,
    list_providers,
    refresh_opencode_providers,
)
from agentbox.core.engines.credentials import CredentialMethod
from agentbox.core.engines.credentials import builtin as _cred_builtin  # noqa: F401 (registers credential methods on import)
from agentbox.core.service.base import Service
from agentbox.core.service.engines import profile_validation

# ponytail bridge — temporary until a dedicated providers service emerges.
from agentbox.core.service.engines.providers import list_provider_models as _free_list_provider_models  # noqa: E402  (ponytail bridge)


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
        return [RunnerProfile(**r) for r in rows]

    def create_profile(self, data: RunnerProfileCreate) -> RunnerProfile:
        """Create a new runner profile.

        Validates every field; derives an id from *name* when none is
        supplied; atomically clears ``is_system_default`` on sibling
        profiles when setting it True.
        """
        profile_validation.validate_create(data)

        if data.id:
            profile_id = data.id
        else:
            existing_ids = {p["id"] for p in self._db.runner_profiles.list_all()}
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
            "api_token_id": data.api_token_id,
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

        return RunnerProfile(**row)

    def get_profile(self, profile_id: str) -> RunnerProfile:
        """Return a single profile, raising ``ProfileNotFound`` if missing."""
        row = self._db.runner_profiles.get_by_id(profile_id)
        if row is None:
            raise ProfileNotFound(profile_id)
        return RunnerProfile(**row)

    def update_profile(
        self, profile_id: str, patch: RunnerProfilePatch
    ) -> RunnerProfile:
        """Partially update a runner profile.

        Validates the supplied fields; atomically clears
        ``is_system_default`` on sibling profiles when setting it True.
        """
        current = self.get_profile(profile_id)
        profile_validation.validate_patch(patch, current_backend=current.backend)

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
        if patch.api_token_id is not None:
            values["api_token_id"] = patch.api_token_id or None
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
        return RunnerProfile(**row)

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
        return RunnerProfile(**row) if row else None

    # ------------------------------------------------------------------
    # Agent ↔ profile binding
    # ------------------------------------------------------------------

    def get_agent_runner_profile(self, agent_id: str) -> RunnerProfile | None:
        """Return the profile bound to *agent_id*, or None."""
        row = self._db.runner_profiles.get_agent_profile(agent_id)
        return RunnerProfile(**row) if row else None

    def set_agent_runner_profile(
        self, agent_id: str, profile_id: str
    ) -> RunnerProfile:
        """Bind a runner profile to an agent (idempotent upsert).

        Returns the full profile data for the bound profile id.
        """
        now = now_iso()
        self._db.runner_profiles.set_agent_profile(
            agent_id, profile_id, created_at=now, updated_at=now,
        )
        return self.get_profile(profile_id)

    def clear_agent_runner_profile(self, agent_id: str) -> None:
        """Remove the profile binding for *agent_id*."""
        self._db.runner_profiles.clear_agent_profile(agent_id)

    # ------------------------------------------------------------------
    # Profile stats (delegates to EvaluationService — plan 093)
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
        from agentbox.core.service.evaluation.service import EvaluationService  # noqa: PLC0415

        if self._db.runner_profiles.get_by_id(profile_id) is None:
            raise ProfileNotFound(profile_id)
        return EvaluationService().runner_profile_stats(profile_id, since=since, until=until)

    def list_profile_stats(
        self,
        since: str | None = None,
        until: str | None = None,
    ) -> list[RunnerProfileStats]:
        """Aggregate stats for all runner profiles."""
        from agentbox.core.service.evaluation.service import EvaluationService  # noqa: PLC0415

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

    def get_runner_provider(self, provider_id: str):
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

        ponytail: delegates to the free-function while a dedicated providers
        service is not yet extracted.
        """
        return await _free_list_provider_models(
            provider_id,
            runner_profiles=self._db.runner_profiles,
            profile_id=profile_id,
            base_url=base_url,
            api_key_env=api_key_env,
            backend=backend,
            refresh=refresh,
        )

    def backends(self) -> dict:
        """Return all registered backends (engine registry)."""
        return list_engines()

    def get_backend(self, name: str):
        """Resolve a backend by name."""
        return resolve_engine_by_name(name)

    def list_backend_names(self) -> list[str]:
        """Sorted names of registered backend adapters."""
        return list_backends()

    # ── Providers (registry passthrough) ──────────────────────────────
    def list_providers(self) -> list[ProviderDescriptor]:
        """All runner provider descriptors."""
        return list_providers()

    def get_provider(self, provider_id: str):
        """Return the provider adapter for *provider_id*, or ``None``."""
        return get_provider(provider_id)

    async def list_provider_models_raw(
        self, provider_id: str, config: Any, refresh: bool = False
    ) -> list[ProviderModel]:
        """List a provider's models via the registry with a resolved config."""
        return await list_models(provider_id, config, refresh=refresh)

    def refresh_opencode_providers(self):
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
