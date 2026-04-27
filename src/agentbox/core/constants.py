"""Agentbox core constants.

Single source of truth for enumerated values used across the codebase.
Avoids magic strings and makes refactoring safer.
"""

from __future__ import annotations

from enum import StrEnum

DEFAULT_RUNNER_TIMEOUT_SECONDS = 1200
"""Fallback runner timeout when ``RenderedConfig.agent_meta`` omits one.

The active DB version's ``timeout_seconds`` must always populate
``agent_meta`` via the backend's ``render()``. This default exists as a
safety net for hand-constructed ``RenderedConfig``s in tests; production
runs should never fall back to it.
"""


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


class RunStatus(StrEnum):
    """Lifecycle status of a run row."""

    RUNNING = "running"
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    INCOMPLETE = "incomplete"


class BundleFile(StrEnum):
    """Conventional file names inside an agent bundle directory."""

    SYSTEM_PROMPT = "prompts/system.md"
    OUTPUT_SCHEMA = "output_schema.json"
    OUTPUT_SCHEMA_ALT = "schema.json"
    INPUT_SCHEMA = "input_schema.json"


class EventType(StrEnum):
    """Discriminator values for RunEvent subclasses.

    These are the wire-format ``type`` strings used in WebSocket messages,
    JSONL transcripts, and API responses.  Keep them in sync with the
    frontend event viewer.
    """

    TEXT = "text"
    LOG = "log"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    USAGE = "usage"
    GUARDRAIL = "guardrail"
    RETRY = "retry"
    THINKING = "thinking"
    TIMEOUT = "timeout"
    DONE = "done"
