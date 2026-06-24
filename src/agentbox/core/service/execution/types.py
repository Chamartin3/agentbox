"""Shared domain types for run services."""

from __future__ import annotations

import logging

from agentbox.core.agents.resolve import (
    engine_load_failure as backend_load_failure,
    list_engines as backends,
)
# NoBackendAvailable imported lazily to avoid circular import.
# executor → service.execution → types → setup (which re-exports from init_run → ExecutionService)

logger = logging.getLogger(__name__)


class RunNotFound(LookupError):
    """Raised when no run exists for ``run_id``."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"unknown run {run_id!r}")
        self.run_id = run_id


class InvalidRunInput(ValueError):
    """Raised when the run dispatch payload is missing required fields."""


class AgentDisabled(RuntimeError):
    """Raised by the run dispatcher when the target agent is disabled.

    ``disabled_at`` is the canonical timestamp from ``agent_meta``. The
    string form is the single, transport-agnostic message — REST, MCP
    and the web UI all surface it verbatim.
    """

    def __init__(self, agent_id: str, disabled_at: str | None) -> None:
        self.agent_id = agent_id
        self.disabled_at = disabled_at
        when = f" (disabled at {disabled_at})" if disabled_at else ""
        super().__init__(
            f"agent {agent_id!r} is disabled{when}; "
            "re-enable it to dispatch runs."
        )


def no_backend_detail(exc: "NoBackendAvailable") -> str:
    """Compose an honest 'why is no backend available' message."""
    loaded = set(backends().keys())
    parts: list[str] = []
    for name in exc.attempted:
        failure = backend_load_failure(name)
        if failure is not None:
            parts.append(f"{name!r} failed to load at startup: {failure}")
        elif name not in loaded:
            parts.append(f"{name!r} is not a registered backend")
        else:
            parts.append(f"{name!r} failed to instantiate")
    why = "; ".join(parts) if parts else "no backend candidates were derived"
    return (
        f"agent {exc.agent_id!r}: cannot dispatch — {why}. "
        f"Registered backends: {sorted(loaded)}."
    )
