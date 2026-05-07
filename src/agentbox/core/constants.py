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
    CODEX = "codex"
    PI = "pi"
    TOKEN = "token"
    HTTP = "http"
    SUBPROCESS = "subprocess"
    ADAPTER = "adapter"


class SessionMode(StrEnum):
    """Session lifetime modes."""

    HEADLESS = "headless"
    PERSISTENT = "persistent"


class RunStatus(StrEnum):
    """Lifecycle status of a run row.

    Terminal status taxonomy (these are NOT overlapping — pick the
    most specific one):

    - ``ok``         — the run completed and the agent produced a valid
                       result.
    - ``failed``     — expected, agent-level task failure: output
                       validation rejected the result, the upstream
                       provider returned a rate-limit / quota / auth
                       error, or the webhook delivering the response
                       could not be submitted. The agent ran; the work
                       didn't succeed.
    - ``timeout``    — the run exceeded its configured ``timeout_seconds``
                       and was killed by the executor.
    - ``error``      — unexpected executor or runner crash. Reserve for
                       genuine bugs in agentbox itself; anything we can
                       classify as agent-level should go to ``failed``
                       and anything operator-/infra-level to
                       ``incomplete``.
    - ``incomplete`` — the agent was interrupted before it could finish:
                       the agentbox process / container died mid-run, an
                       operator cancelled the run, or the executor task
                       was otherwise torn down. The agent itself did not
                       fail — the run was simply never allowed to
                       complete. Reaped on startup.

    ``stopped`` was a transitional alias for ``incomplete``; new code
    must not emit it.
    """

    RUNNING = "running"
    OK = "ok"
    ERROR = "error"
    FAILED = "failed"
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
    VALIDATION = "validation"
    DONE = "done"


def runtime_default_model(backend_name: str) -> str | None:
    """Look up an operator-configured default model for a backend.

    Reads the `runtime_defaults` settings section for `default_model_<backend>`.
    Returns `None` when the store isn't available, the section is missing,
    or the value is unset. Backends fall back to their hard-coded
    `default_model` attribute when this returns `None`.
    """
    try:
        from agentbox.api.deps import get_store

        store = get_store()
        section = store.get_settings_section("runtime_defaults") or {}
        value = section.get(f"default_model_{backend_name}")
        if isinstance(value, str) and value.strip():
            return value
        return None
    except Exception:
        return None
