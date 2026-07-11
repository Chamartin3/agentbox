"""Run-execution domain errors."""

from __future__ import annotations


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
