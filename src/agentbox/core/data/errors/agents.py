"""Agent-domain service errors.

Part of the agent service's error contract (REST/MCP/CLI all catch these),
so they live at the shapes leaf rather than beside the service.
``PromptError`` is NOT here — it belongs to the prompt-versioning surface
in ``core.agents.versioning.prompts``.
"""

from __future__ import annotations

from typing import Any


class AgentServiceError(Exception):
    """Carries an HTTP-shaped (status_code, code, detail) triple."""

    def __init__(self, status_code: int, code: str, detail: Any) -> None:
        super().__init__(f"{code}: {detail}")
        self.status_code = status_code
        self.code = code
        self.detail = detail


class AgentNotFound(LookupError):
    """Raised when no ``AgentDef`` can be resolved for ``agent_id``."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(f"unknown agent {agent_id!r}")
        self.agent_id = agent_id


class AgentAlreadyExists(ValueError):
    """Raised when create_agent_record is called for an existing agent_id."""


class VersionNotFound(LookupError):
    pass


class VersionNotDraft(ValueError):
    pass


class DuplicateVersionFile(ValueError):
    """Same sha256 or relative_path already attached to the draft version."""


class VersionFileNotFound(LookupError):
    pass
