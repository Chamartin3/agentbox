"""Build the immutable runner snapshot attached to a run row."""

from __future__ import annotations
from typing import Any

import logging
from agentbox.core.data import AgentDef, RunnerSnapshot, now_iso
from agentbox.core.db import RunnerProfileManager
from agentbox.core.engines.profiles import EffectiveRunnerConfig

logger = logging.getLogger(__name__)


def build_runner_snapshot(
    runner_profiles: "RunnerProfileManager",
    *,
    effective: EffectiveRunnerConfig,
    rendered_model: str | None,
    backend_override: str | None,
    runner_override: str | None,
    runner_profile_id_param: str | None,
    runner_config_param: dict[str, Any] | None,
    timeout_override: int | None,
    agent: AgentDef,
) -> RunnerSnapshot:
    """Compose the append-only ``runner_snapshot`` dict for a run."""
    profile_name: str | None = None
    if effective.profile_id:
        try:
            row = runner_profiles.get_by_id(effective.profile_id)
            if row is not None:
                profile_name = row.name
        except Exception:
            logger.debug(
                "could not resolve profile name for %s", effective.profile_id
            )

    overrides_applied: dict[str, Any] = {}
    if backend_override:
        overrides_applied["backend"] = backend_override
    if runner_override:
        overrides_applied["runner_kind"] = runner_override
    if runner_profile_id_param:
        overrides_applied["runner_profile_id"] = runner_profile_id_param
    if runner_config_param:
        overrides_applied["runner_config"] = runner_config_param
    if timeout_override:
        overrides_applied["timeout_seconds"] = timeout_override

    effective_timeout = timeout_override or agent.runner.timeout_seconds

    return {
        "profile_id": effective.profile_id,
        "profile_name": profile_name,
        "backend": effective.backend,
        "model": rendered_model or effective.model,
        "timeout_seconds": effective_timeout,
        "provider": effective.provider,
        "extra_args": list(effective.extra_args or []),
        "source": effective.source,
        "overrides_applied": overrides_applied,
        "captured_at": now_iso(),
    }


__all__ = ["build_runner_snapshot"]
