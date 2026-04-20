"""Agentbox core constants.

Single source of truth for enumerated values used across the codebase.
Avoids magic strings and makes refactoring safer.
"""

from __future__ import annotations

from enum import Enum


class RunnerKind(str, Enum):
    """Supported agent runner implementations."""

    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"
    PYDANTIC_AI = "pydantic_ai"
    HTTP = "http"
    SUBPROCESS = "subprocess"
    ADAPTER = "adapter"

    def __str__(self) -> str:
        return self.value


class SessionMode(str, Enum):
    """Session lifetime modes."""

    HEADLESS = "headless"
    PERSISTENT = "persistent"

    def __str__(self) -> str:
        return self.value
