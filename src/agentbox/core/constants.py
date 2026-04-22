"""Agentbox core constants.

Single source of truth for enumerated values used across the codebase.
Avoids magic strings and makes refactoring safer.
"""

from __future__ import annotations

from enum import StrEnum


class RunnerKind(StrEnum):
    """Supported agent runner implementations."""

    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"
    PYDANTIC_AI = "pydantic_ai"
    HTTP = "http"
    SUBPROCESS = "subprocess"
    ADAPTER = "adapter"


class SessionMode(StrEnum):
    """Session lifetime modes."""

    HEADLESS = "headless"
    PERSISTENT = "persistent"
