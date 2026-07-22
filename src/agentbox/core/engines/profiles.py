"""Effective runner configuration resolution.

EffectiveRunnerConfig represents the runtime configuration for a run,
resolved from precedence: per-run overrides > profiles > agent-bound
profile > system default > agent legacy > backend default.

RunnerProfileResolver implements the resolution logic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agentbox.core.data.payload_types import ModelParams
from agentbox.core.engines.backends.registry import get_backend as resolve_engine_by_name
from agentbox.core.engines.providers import get_provider
from agentbox.core.db import RunnerProfileManager
from agentbox.core.data.profiles import RunnerProfile

SourceType = Literal[
    "run_override",
    "run_profile",
    "agent_profile",
    "system_default",
]

# Terminal fallback backend when no runner profile resolves at all. The runner
# profile cascade (per-run → profile → agent-bound → system-default) is the
# real source of truth; this only keeps the resolver total.
_DEFAULT_BACKEND = "token"


class EffectiveRunnerConfig(BaseModel):
    """Resolved runtime configuration for a runner.

    Fields present in this config override the agent's defaults.
    The `source` field indicates which resolution path was taken.
    """

    backend: str | None = None
    """Resolved backend name (e.g. 'claude_code', 'token')."""

    provider: str | None = None
    """Provider identifier (e.g. 'openai', 'openrouter')."""

    model: str | None = None
    """Model identifier, typically provider-prefixed (e.g. 'openai:gpt-4o')."""

    timeout_seconds: int | None = None
    """Execution timeout in seconds."""

    base_url: str | None = None
    """Custom base URL for HTTP providers."""

    api_key_env: str | None = None
    """Environment variable name for API credentials (not the value)."""

    output_mode: str = "auto"
    """How the token backend should enforce structured output:
    ``auto`` (current tool-call behavior), ``tool``, ``prompted``, or
    ``native``. Only the token backend reads this."""

    params: ModelParams = Field(default_factory=ModelParams)
    """Provider-specific parameters (merged from profile + per-run)."""

    headers: dict[str, str] = Field(default_factory=dict)
    """Custom HTTP headers (merged from profile + per-run)."""

    extra_args: list[str] = Field(default_factory=list)
    """Additional CLI arguments for the runner."""

    profile_id: str | None = None
    """Source profile ID, if resolved from a profile."""

    source: SourceType = "run_override"
    """How this config was resolved."""


def effective_backend(agent: Any, runner_profiles: RunnerProfileManager) -> str:
    """The agent's effective backend — a backend projection of the one resolver.

    Runs ``RunnerProfileResolver.resolve()`` with no per-run overrides
    (agent-bound profile → system-default → ``the module-level default backend``) and
    returns its backend. The single place non-run callers read "the agent's
    backend"; it never consults ``runner.kind``. Takes ``runner_profiles`` so
    callers reuse their own DB handle instead of constructing a service.
    """
    eff = RunnerProfileResolver().resolve(
        agent=agent,
        runner_profiles=runner_profiles,
        runner_profile_id=None,
        runner_config=None,
        backend_override=None,
        timeout_seconds=None,
    )
    return eff.backend or _DEFAULT_BACKEND


class RunnerProfileResolver:
    """Resolves effective runner config from multiple sources.

    Precedence (first match wins):
    1. Per-run runner_config dict / explicit backend or timeout override
    2. Per-run runner_profile_id
    3. Agent-bound runner profile
    4. System default runner profile
    5. _DEFAULT_BACKEND (terminal — the resolver is total)

    AgentDef.runner is intentionally not consulted here. The resolved
    EffectiveRunnerConfig is the only runtime dispatch source of truth.
    """

    def resolve(
        self,
        *,
        agent: Any,  # AgentDef — duck-typed
        runner_profiles: RunnerProfileManager,
        runner_profile_id: str | None,
        runner_config: dict[str, Any] | None,
        backend_override: str | None,
        timeout_seconds: int | None,
    ) -> EffectiveRunnerConfig:
        """Resolve the effective runner configuration.

        Args:
            agent: AgentDef instance (duck-typed, not imported directly).
            runner_profiles: RunnerProfileManager for profile DB lookups.
            runner_profile_id: Explicit profile ID from the run request.
            runner_config: Inline config dict from the run request.
            backend_override: Per-run backend override.
            timeout_seconds: Per-run timeout override.

        Returns:
            EffectiveRunnerConfig with source attribution.

        Raises:
            ValueError: If a profile is explicitly selected but disabled,
                missing, or backend is invalid.
        """

        # Rule 1: Per-run runner_config dict, or explicit backend/timeout
        # override. This is a transient run-specific config, independent
        # from the static agent definition.
        if runner_config or backend_override:
            data = runner_config or {}
            config = EffectiveRunnerConfig(
                backend=data.get("backend") or backend_override,
                provider=data.get("provider"),
                model=data.get("model"),
                timeout_seconds=data.get("timeout_seconds") or timeout_seconds,
                base_url=data.get("base_url"),
                api_key_env=data.get("api_key_env"),
                output_mode=data.get("output_mode") or "auto",
                params=data.get("params", {}),
                headers=data.get("headers", {}),
                extra_args=data.get("extra_args", []),
                source="run_override",
            )
            # Validate backend if present
            if config.backend:
                self._validate_backend(config.backend)
            return config

        # Rule 2: Per-run runner_profile_id
        if runner_profile_id:
            row = runner_profiles.get_by_id(runner_profile_id)
            if not row:
                raise ValueError(f"runner profile {runner_profile_id!r} not found")
            profile = row
            is_enabled = profile.is_enabled
            if not is_enabled:
                raise ValueError(f"runner profile {runner_profile_id!r} is disabled")
            config = self._build_from_profile(
                profile,
                source="run_profile",
                backend_override=backend_override,
                timeout_override=timeout_seconds,
            )
            return config

        # Rule 3: Agent-bound runner profile
        if hasattr(agent, "id"):
            row = runner_profiles.get_agent_profile(agent.id)
            if row:
                profile = row
                is_enabled = profile.is_enabled
                if is_enabled:
                    config = self._build_from_profile(
                        profile,
                        source="agent_profile",
                        backend_override=backend_override,
                        timeout_override=timeout_seconds,
                    )
                    return config
                # Disabled agent-bound profile: fall through to next rules

        # Rule 4: System default runner profile
        row = runner_profiles.get_system_default()
        if row:
            profile = row
            config = self._build_from_profile(
                profile,
                source="system_default",
                backend_override=backend_override,
                timeout_override=timeout_seconds,
            )
            return config

        # Rule 5: terminal fallback — the module-level default backend.
        # Keeps the resolver total: it always yields a backend, so no caller
        # ever needs to consult the legacy per-agent ``runner.kind``.
        return EffectiveRunnerConfig(
            backend=backend_override or _DEFAULT_BACKEND,
            timeout_seconds=timeout_seconds,
            source="run_override",
        )

    def _build_from_profile(
        self,
        profile: RunnerProfile,
        source: SourceType,
        backend_override: str | None = None,
        timeout_override: int | None = None,
    ) -> EffectiveRunnerConfig:
        """Build EffectiveRunnerConfig from a RunnerProfile model.

        Args:
            profile: RunnerProfile Pydantic model with backend, model, etc.
            source: Attribution source.
            backend_override: Per-run backend override (applied last).
            timeout_override: Per-run timeout override (applied last).

        Returns:
            Fully populated EffectiveRunnerConfig.
        """
        config = EffectiveRunnerConfig(
            backend=profile.backend,
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key_env=profile.api_key_env,
            output_mode=profile.output_mode or "auto",
            params=profile.params,
            headers=profile.headers,
            extra_args=profile.extra_args,
            profile_id=profile.id,
            source=source,
        )

        # Overlay provider descriptor defaults for any unset routing fields.
        if config.provider:
            adapter = get_provider(config.provider)
            if adapter is not None:
                desc = adapter.descriptor
                if config.base_url is None and desc.default_base_url:
                    config.base_url = desc.default_base_url
                if config.api_key_env is None and desc.default_api_key_env:
                    config.api_key_env = desc.default_api_key_env

        # Apply per-run overrides (last-mile)
        if backend_override:
            config.backend = backend_override
        if timeout_override:
            config.timeout_seconds = timeout_override

        return config

    def _validate_backend(self, backend: str) -> None:
        """Validate that backend is registered.

        Args:
            backend: Backend name to validate.

        Raises:
            ValueError: If backend is not registered.
        """
        try:
            resolve_engine_by_name(backend)
        except KeyError as exc:
            raise ValueError(f"unknown backend {backend!r}: {exc}") from exc
