"""Effective runner configuration resolution.

EffectiveRunnerConfig represents the runtime configuration for a run,
resolved from precedence: per-run overrides > profiles > agent-bound
profile > system default > agent legacy > backend default.

RunnerProfileResolver implements the resolution logic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agentbox.core.plugins import get_backend
from agentbox.core.providers import get_provider

SourceType = Literal[
    "run_override",
    "run_profile",
    "agent_profile",
    "system_default",
    "agent_legacy",
    "backend_default",
]


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

    params: dict[str, Any] = Field(default_factory=dict)
    """Provider-specific parameters (merged from profile + per-run)."""

    headers: dict[str, str] = Field(default_factory=dict)
    """Custom HTTP headers (merged from profile + per-run)."""

    extra_args: list[str] = Field(default_factory=list)
    """Additional CLI arguments for the runner."""

    profile_id: str | None = None
    """Source profile ID, if resolved from a profile."""

    source: SourceType = "backend_default"
    """How this config was resolved."""


class RunnerProfileResolver:
    """Resolves effective runner config from multiple sources.

    Precedence (first match wins):
    1. Per-run runner_config dict
    2. Per-run runner_profile_id
    3. Agent-bound runner profile
    4. System default runner profile
    5. Agent's legacy runner spec
    6. Backend defaults
    """

    def resolve(
        self,
        *,
        agent: Any,  # AgentDef — duck-typed
        store: Any,  # SessionStore — duck-typed
        runner_profile_id: str | None,
        runner_config: dict[str, Any] | None,
        backend_override: str | None,
        timeout_seconds: int | None,
    ) -> EffectiveRunnerConfig:
        """Resolve the effective runner configuration.

        Args:
            agent: AgentDef instance (duck-typed, not imported directly).
            store: SessionStore instance (duck-typed, not imported directly).
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

        # Rule 1: Per-run runner_config dict (non-empty)
        if runner_config:
            config = EffectiveRunnerConfig(
                backend=runner_config.get("backend") or backend_override,
                provider=runner_config.get("provider"),
                model=runner_config.get("model"),
                timeout_seconds=runner_config.get("timeout_seconds") or timeout_seconds,
                base_url=runner_config.get("base_url"),
                api_key_env=runner_config.get("api_key_env"),
                params=runner_config.get("params", {}),
                headers=runner_config.get("headers", {}),
                extra_args=runner_config.get("extra_args", []),
                source="run_override",
            )
            # Validate backend if present
            if config.backend:
                self._validate_backend(config.backend)
            return config

        # Rule 2: Per-run runner_profile_id
        if runner_profile_id:
            profile = store.get_runner_profile(runner_profile_id)
            if not profile:
                raise ValueError(
                    f"runner profile {runner_profile_id!r} not found"
                )
            is_enabled = (
                getattr(profile, "is_enabled", True)
                if hasattr(profile, "is_enabled")
                else profile.get("is_enabled", True)
            )
            if not is_enabled:
                raise ValueError(
                    f"runner profile {runner_profile_id!r} is disabled"
                )
            config = self._build_from_profile(
                profile,
                source="run_profile",
                backend_override=backend_override,
                timeout_override=timeout_seconds,
            )
            return config

        # Rule 3: Agent-bound runner profile
        if hasattr(agent, "id"):
            profile = store.get_agent_runner_profile(agent.id)
            if profile:
                is_enabled = (
                    getattr(profile, "is_enabled", True)
                    if hasattr(profile, "is_enabled")
                    else profile.get("is_enabled", True)
                )
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
        profile = store.get_system_default_runner_profile()
        if profile:
            config = self._build_from_profile(
                profile,
                source="system_default",
                backend_override=backend_override,
                timeout_override=timeout_seconds,
            )
            return config

        # Rule 5: Agent's legacy runner spec
        if hasattr(agent, "runner") and agent.runner:
            runner = agent.runner
            config = EffectiveRunnerConfig(
                backend=getattr(runner, "kind", None),
                model=getattr(runner, "model", None),
                timeout_seconds=getattr(runner, "timeout_seconds", None),
                extra_args=getattr(runner, "extra_args", []),
                source="agent_legacy",
            )
            # Apply per-run overrides
            if backend_override:
                config.backend = backend_override
            if timeout_seconds:
                config.timeout_seconds = timeout_seconds
            return config

        # Rule 6: Backend defaults
        config = EffectiveRunnerConfig(source="backend_default")
        if backend_override:
            config.backend = backend_override
        if timeout_seconds:
            config.timeout_seconds = timeout_seconds
        return config

    def _build_from_profile(
        self,
        profile: dict[str, Any] | Any,
        source: SourceType,
        backend_override: str | None = None,
        timeout_override: int | None = None,
    ) -> EffectiveRunnerConfig:
        """Build EffectiveRunnerConfig from a profile dict or object.

        Args:
            profile: Profile data dict or Pydantic model with backend, model, etc.
            source: Attribution source.
            backend_override: Per-run backend override (applied last).
            timeout_override: Per-run timeout override (applied last).

        Returns:
            Fully populated EffectiveRunnerConfig.
        """
        # Convert Pydantic model to dict if needed
        if hasattr(profile, "model_dump"):
            profile_dict = profile.model_dump(exclude_none=False)
        elif hasattr(profile, "dict"):
            profile_dict = profile.dict()
        else:
            profile_dict = dict(profile) if not isinstance(profile, dict) else profile

        config = EffectiveRunnerConfig(
            backend=profile_dict.get("backend"),
            provider=profile_dict.get("provider"),
            model=profile_dict.get("model"),
            timeout_seconds=profile_dict.get("timeout_seconds"),
            base_url=profile_dict.get("base_url"),
            api_key_env=profile_dict.get("api_key_env"),
            params=profile_dict.get("params", {}),
            headers=profile_dict.get("headers", {}),
            extra_args=profile_dict.get("extra_args", []),
            profile_id=profile_dict.get("id"),
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
            get_backend(backend)
        except KeyError as exc:
            raise ValueError(
                f"unknown backend {backend!r}: {exc}"
            ) from exc
