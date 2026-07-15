"""Agentbox core constants.

Single source of truth for enumerated values used across the codebase.
Avoids magic strings and makes refactoring safer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self


class CatalogEnum(StrEnum):
    """StrEnum that is its own validation catalog."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(e.value for e in cls)

    @classmethod
    def coerce(cls, value: str, *, label: str = "value") -> Self:
        try:
            return cls(value)
        except ValueError:
            raise ValueError(
                f"{label} must be one of {', '.join(cls.values())}"
            ) from None


class BackendName(CatalogEnum):
    """Canonical names of the built-in backend adapters / recipe engines.

    These MUST match the keys under ``[project.entry-points."agentbox.backends"]``
    in pyproject.toml — that registry is the runtime catalog (and the only place
    plugin-provided backends appear). This enum names the built-ins so callers
    use ``BackendName.CLAUDE_CODE`` instead of the literal ``"claude_code"``.
    """

    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"
    TOKEN = "token"
    CODEX = "codex"
    PI = "pi"

    @property
    def label(self) -> str:
        """Human-readable display label."""
        return _BACKEND_LABELS[self]

    @property
    def runner_kind(self) -> str:
        """RunnerKind string passed to ``_launch_session``."""
        return _BACKEND_RUNNER_MAP[self]

    @classmethod
    def label_for(cls, name: str, /) -> str:
        """Human-readable label for *name*, falling back to *name* itself."""
        try:
            return cls(name).label
        except ValueError:
            return name

    @classmethod
    def runner_for(cls, name: str, /) -> str:
        """RunnerKind for *name*, falling back to *name* itself."""
        try:
            return cls(name).runner_kind
        except ValueError:
            return name


_BACKEND_LABELS: dict[BackendName, str] = {
    BackendName.CLAUDE_CODE: "Claude Code (CLI)",
    BackendName.OPENCODE: "OpenCode (CLI)",
    BackendName.CODEX: "OpenAI Codex (CLI)",
    BackendName.PI: "pi.dev (CLI)",
    BackendName.TOKEN: "Token / pydantic-ai (in-process)",
}

_BACKEND_RUNNER_MAP: dict[BackendName, str] = {
    BackendName.CLAUDE_CODE: "claude",
    BackendName.OPENCODE: "opencode",
    BackendName.CODEX: "codex",
    BackendName.PI: "pi",
    BackendName.TOKEN: "token",
}


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

    @property
    def is_running(self) -> bool:
        return self is RunStatus.RUNNING


# The terminal status a ``DoneEvent`` / stream session reports. Defined
# once here so the subset isn't re-spelled as a bare Literal at each use.
TerminalRunStatus = Literal[
    RunStatus.OK, RunStatus.ERROR, RunStatus.TIMEOUT, RunStatus.FAILED
]

# The coarse run states the activity feed filters by.
ActivityStateFilter = Literal[RunStatus.RUNNING, RunStatus.OK, RunStatus.ERROR]


class BundleFile(StrEnum):
    """Conventional file names inside an agent bundle directory."""

    SYSTEM_PROMPT = "prompts/system.md"
    OUTPUT_SCHEMA = "output_schema.json"
    OUTPUT_SCHEMA_ALT = "schema.json"
    INPUT_SCHEMA = "input_schema.json"


class ResourceType(CatalogEnum):
    """Allowed values for ``repo_resources.type``.

    Mirrors the ``resources_type_check`` CHECK constraint on the ``Resource``
    entity (``core/db/resources/resource.py``).
    """

    DOCUMENT = "document"
    FOLDER = "folder"
    SKILL = "skill"
    SCHEMA = "schema"
    SCRIPT = "script"

    @property
    def is_multi_file(self) -> bool:
        return self in (ResourceType.FOLDER, ResourceType.SKILL)

    @property
    def is_single_file(self) -> bool:
        return not self.is_multi_file

    @property
    def default_extension(self) -> str:
        return {
            ResourceType.DOCUMENT: ".md",
            ResourceType.SCHEMA: ".json",
            ResourceType.SCRIPT: "",
        }.get(self, "")


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
    RETRY = "retry"
    THINKING = "thinking"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    DONE = "done"


class MessageRole(StrEnum):
    """Conversation message roles, shared across backend conversation
    decoders and the ``TextEvent`` wire format."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ContentBlockType(StrEnum):
    """Kinds of content part inside a parsed conversation turn."""

    TEXT = "text"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class ValidationMode(StrEnum):
    """Output-validation engine selection."""

    JSONSCHEMA = "jsonschema"
    PYDANTIC = "pydantic"
    BOTH = "both"
    NONE = "none"


# Engines a config can *select* (always picks one — ``none`` is a runtime
# outcome on ``ValidationEvent``, not a configurable choice).
ConfiguredValidationMode = Literal[
    ValidationMode.JSONSCHEMA, ValidationMode.PYDANTIC, ValidationMode.BOTH
]


class LogLevel(StrEnum):
    """Severity for ``LogEvent`` and stream-session logging."""

    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class PromptMode(CatalogEnum):
    """How a prompt-resource binding is embedded into the prompt."""

    INLINE = "inline"
    SKILL_PRIMER = "skill_primer"
    NAME_ONLY = "name_only"
    MANIFEST = "manifest"


class PromptSlot(CatalogEnum):
    """Which prompt slot a binding targets."""

    SYSTEM = "system"
    USER_TEMPLATE = "user_template"
    INPUT_SCHEMA = "input_schema"
    OUTPUT_SCHEMA = "output_schema"


class McpPolicy(CatalogEnum):
    """Default workspace MCP allow/deny policy."""

    ALLOW_ALL_UNLESS_DISABLED = "allow_all_unless_disabled"
    DENY_ALL_UNLESS_ENABLED = "deny_all_unless_enabled"


class ValidatorKind(CatalogEnum):
    """Kinds of output/input validators in agent config."""

    HTTP = "http"
    SCRIPT = "script"


class ImportSource(CatalogEnum):
    """How a resource version was imported into the store."""

    UPLOAD = "upload"
    HOST_PATH = "host_path"
    TOML_MIGRATION = "toml_migration"
    DB_ONLY = "db_only"


class MaterializeMode(CatalogEnum):
    """How a resource is materialized into a workspace file tree."""

    COPY = "copy"
    SYMLINK = "symlink"
    MOUNT = "mount"


class OnConflict(CatalogEnum):
    """Behaviour when materializing a resource would overwrite an existing file."""

    ERROR = "error"
    OVERWRITE = "overwrite"
    SKIP = "skip"


class ValidationCheckMode(CatalogEnum):
    """Aggressiveness of output schema checks during run composition."""

    STRICT = "strict"
    WARN = "warn"
    OFF = "off"


class RunnerKind(CatalogEnum):
    """Supported interactive runner backends for ``agentbox launch``."""

    CLAUDE = "claude"
    OPENCODE = "opencode"
    CODEX = "codex"
    PI = "pi"
    SHELL = "shell"


# ── MCP server names ──────────────────────────────────────────────────────────

HOST_ENV_SERVER_NAME: str = "agentbox-host-env"
"""Canonical name for the host-env stdio MCP server.

Every consumer (Claude's .mcp.json, the token backend's pydantic-ai toolset)
spawns the same server under this name.
"""

AGENT_TOOLS_SERVER_NAME: str = "agentbox-agent-tools"
"""Canonical name for the agent-tools stdio MCP server."""

MCP_FILENAME: str = ".mcp.json"
"""Canonical filename for Claude's native MCP server config in a run dir.

Cross-domain constant: consumed by both the claude_code engine adapter and
the workspaces layer. Lives here (the leaf) so neither domain imports the
other.
"""
