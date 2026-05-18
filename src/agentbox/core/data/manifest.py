"""Declarative agent + workspace models loaded from agentbox.toml.

These are the parsed shapes — not persisted to SQLite. The loader logic
lives in ``agentbox.core.deprecated.definitions.loader``; this module only defines
the typed structures.
"""

from __future__ import annotations

import enum
import warnings
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentbox.core.constants import RunnerKind, SessionMode

McpTransport = Literal["http", "sse", "stdio"]


class AgentSource(enum.StrEnum):
    """Format and location of an agent definition's source file."""

    INLINE_TOML = "inline_toml"
    """Agent defined as an ``[[agents]]`` block inside ``agentbox.toml``."""
    STANDALONE_TOML = "standalone_toml"
    """Agent defined in a separate ``.toml`` file under ``agents.d/``."""
    MARKDOWN = "markdown"
    """Agent defined as a markdown file with YAML frontmatter under ``agents.d/``."""
    LEGACY_DIR = "legacy_dir"
    """Agent defined via the legacy ``agents/<name>/agent.toml`` + ``prompts/system.md`` pattern."""
    BUNDLE = "bundle"
    """Agent defined as a bundle directory: ``<bundle_dir>/<id>/agent.toml`` with
    a ``[composition]`` block declaring system prompt, references, and schemas."""


class McpServerSpec(BaseModel):
    """Specification for a single MCP server.

    Exactly one of ``url`` or ``command`` must be set — remote servers
    use a URL; local servers use a command array.
    """

    name: str = "mcp"
    """Unique identifier for this MCP server (e.g. ``my-mcp``)."""

    url: str | None = None
    """HTTP/SSE endpoint for a remote MCP server."""

    transport: McpTransport = "http"
    """Transport protocol. Only consulted when ``url`` is set."""

    command: list[str] | None = None
    """Command array for stdio transport (e.g. ``["mcp_serve.sh"]``)."""

    cache_ttl: int = 300
    """In-memory cache TTL in seconds (default 5 min)."""

    @model_validator(mode="after")
    def _validate_oneof(self) -> McpServerSpec:
        has_url = self.url is not None
        has_cmd = self.command is not None
        if has_url == has_cmd:
            raise ValueError(
                f"McpServerSpec({self.name}): exactly one of url/command must be set"
            )
        return self


# ---------------------------------------------------------------------------
# Runtime agent + workspace shapes
# ---------------------------------------------------------------------------


class RunnerSpec(BaseModel):
    kind: RunnerKind = RunnerKind.TOKEN
    """Which backend to dispatch to (deprecated — use ``backend`` on the
    run request or ``backend_preference`` on the project manifest instead).

    The loader still reads this for backwards compatibility, mapping it
    onto the corresponding backend adapter name. A ``DeprecationWarning``
    is emitted when an agent definition relies on ``kind``.
    """

    # --- Shared across all runners ---

    timeout_seconds: int = 1200
    """Run timeout in seconds. The agent's runner config is the single source
    of truth — runner profiles do not carry a timeout. A per-run override on
    ``POST /api/runs`` wins over this value."""

    extra_args: list[str] = Field(default_factory=list)
    """Extra CLI args passed verbatim (claude_code / opencode only)."""

    # --- claude_code runner ---

    model: str | None = None
    """Model alias passed to the runner (claude only)."""

    mcp_config_path: str | None = None
    """Path to mcp config json, resolved relative to project_root.

    This is the *global* MCP server configuration (e.g. which MCP
    servers to connect to). Per-workspace generated configs
    (agents.json, settings.json) are resolved automatically from the
    workspace directory at runtime.
    """

    allowed_tools: list[str] = Field(default_factory=list)
    """Claude-only: --allowedTools args."""

    # --- opencode runner ---

    # config_path removed — opencode config is now generated per-workspace.

    # --- token runner ---

    agent_module: str | None = None
    """Python import path to the pydantic-ai Agent class.

    Format: ``module.path:ClassName`` (e.g.
    ``agents.company_researcher.agent:CompanyResearcherAgent``).

    When unset but ``prompt_path`` is provided on the ``AgentDef``,
    a minimal agent is auto-generated from the markdown.
    """

    # --- token direct-Agent dependencies ---

    deps_factory: str | None = None
    """Dotted import path ``module.path:callable`` that constructs the
    ``deps`` object passed to a ``pydantic_ai.Agent.run_sync(deps=...)``
    call. Resolved at run time."""

    # --- Output validation & retry ---

    output_schema_path: str | None = None

    output_validation_engine: Literal["jsonschema", "pydantic", "both"] = "both"
    """Which engine(s) to use when validating output against the schema.

    ``"jsonschema"`` — jsonschema only (legacy behaviour).
    ``"pydantic"`` — pydantic_core only (stricter type checks).
    ``"both"`` — jsonschema first, then pydantic (default, strictest).
    """

    max_validation_retries: int = 0
    max_error_retries: int = 0
    """How many times to re-run the agent when the run fails with an error
    (excluding timeouts and validation failures, which have their own retry
    configuration)."""


class GuardrailRef(BaseModel):
    """Entrypoint name registered under `agentbox.guardrails`."""

    name: str
    options: dict = Field(default_factory=dict)


class SharedRef(BaseModel):
    """Reference to a shared resource (versioned, stored in DB).

    When used in composition references, system prompt, or schemas, the
    shared resource is resolved at run time via SessionStore.
    """

    shared: str
    """Resource id, e.g. 'schema/job-eval-v3', 'guideline/resume-rules'."""

    version: int | None = None
    """Optional specific version; None = use active version."""

    model_config = ConfigDict(extra="forbid")


class WorkspaceFile(BaseModel):
    """File mapping for workspace composition."""

    src: str
    """Source path (project-relative)."""

    dst: str
    """Destination path (workspace-relative)."""


class WorkspaceDef(BaseModel):
    """Named workspace definition from agentbox.toml."""

    name: str
    """Unique identifier used by agents to reference this workspace."""

    path: str
    """Project-relative path to the workspace directory."""

    description: str = ""
    """Human-readable description."""

    skills: list[str] = Field(default_factory=list)
    """Optional list of skill IDs to include (by name).

    Empty list means auto-discover all skills under workspace/skills/.
    """

    permissions: str | None = None
    """Deprecated: path to permissions file relative to workspace.

    Permissions are now inlined via allowed_tools, allowed_builtin_tools, etc.
    """

    # --- Inlined permissions (from capabilities.json) ---

    allowed_tools: list[str] = Field(default_factory=list)
    """List of allowed tool names (claude_code runner)."""

    allowed_builtin_tools: list[str] = Field(default_factory=list)
    """List of allowed Claude built-in tool names."""

    files: list[WorkspaceFile] = Field(default_factory=list)
    """Files to copy/mount into the workspace at compose time."""

    max_tokens: int | None = None
    """Maximum tokens for a single run in this workspace."""

    allow_file_write: bool = True
    """Whether agents can write to the workspace filesystem."""

    allow_network: bool = True
    """Whether agents can make network requests."""


class CompositionConfig(BaseModel):
    """Prompt-composition recipe for an agent bundle.

    When present, agentbox owns prompt rendering via
    ``agentbox.core.prompt.composition.compose()``.

    Supports both filesystem paths and shared resource references:
    - File paths: ``"prompts/system.md"`` or ``"shared://root/path.md"``
    - Shared refs: ``{"shared": "resource-id", "version": 2}`` (version optional)
    """

    system: str | SharedRef = "prompts/system.md"
    """System prompt: bundle-relative path, shared:// path, or SharedRef."""

    references: list[str | dict | SharedRef] = Field(default_factory=list)
    """Reference files. Each entry can be a path string, a dict with ``path``
    and optional ``heading``, or a SharedRef."""

    user_template: str | SharedRef | None = None
    """User template: path string or SharedRef. When unset,
    ``variables["user_message"]`` is used verbatim."""

    input_schema: str | SharedRef | None = None
    """Input schema: path string or SharedRef."""

    output_schema: str | SharedRef | None = None
    """Output schema: path string or SharedRef."""

    transport: str = "system_message"
    """How the composed system prompt is delivered to the runner.
    E.g. ``system_message``, ``file`` (CLAUDE.md), etc."""

    output_validation: str = "strict"
    """One of ``strict`` | ``warn`` | ``off``."""


class AgentDef(BaseModel):
    id: str
    """Stable identifier (e.g. `myproject.draft_writer`)."""

    description: str = ""
    prompt_path: str | None = None
    """Project-relative path to system prompt markdown.

    For ``token`` runners without an explicit ``agent_module``,
    this markdown is used to auto-generate a minimal agent.

    .. deprecated::
       Use ``[composition]`` instead.
    """

    prompt: str | None = None
    """Inline system prompt text. Mutually exclusive with ``prompt_path`` —
    when both are set, ``prompt`` wins."""

    composition: CompositionConfig | None = None
    """Prompt-composition recipe. When present, takes precedence over
    ``prompt_path`` / ``prompt``."""

    workspace: str | None = None
    """Workspace reference.

    Resolution:
    - Named workspace: "default", "research" (looked up in workspaces table)
    - Explicit path: "workdir/agentbox/ws/foo"
    - "<ephemeral>": fresh tmp dir per run, deleted after (sandbox mode).
    - Omitted: auto-resolved to ``<workspaces_root>/<agent_id>/``.
    """

    runner: RunnerSpec = Field(default_factory=lambda: RunnerSpec())
    session_mode: SessionMode = "headless"
    guardrails: list[GuardrailRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    unsupported_backends: list[str] = Field(default_factory=list)
    """Backend names that this agent cannot run on. When set, those
    backends are skipped during automatic backend selection (see
    ``backend_preference`` on ``ProjectManifest``)."""

    claude_agent: bool = True
    """False means pydantic-only — no external Claude/OpenCode config."""

    headless: bool = False
    """True means no interactive tools — the agent receives the prompt via
    stdin and emits JSON to stdout."""

    tools: list[str] = Field(default_factory=list)
    """Tool names / ``@group`` references for the Claude/OpenCode agent profile."""

    webhook_url: str | None = None
    """Optional URL agentbox POSTs to when a run for this agent reaches a
    terminal state (ok/error). Body: {run_id, agent_id, status, output,
    error, started_at, finished_at, usage, duration_ms}. Failures are
    retried a few times then logged.

    If unset, falls back to Settings.completion_webhook_url (env var
    AGENTBOX_COMPLETION_WEBHOOK_URL). Set to empty string to opt out when
    a global default is configured."""

    source_path: Path | None = None
    """Absolute path to the source file this agent was loaded from.

    Used by ``ManifestWriter`` to dispatch to the correct writer.
    Set automatically by ``DefinitionLoader``; *None* for agents
    created programmatically without a backing file.
    """

    source_format: AgentSource | None = None
    """Format of the source file (inline TOML, standalone TOML, markdown).

    Set automatically by ``DefinitionLoader``; *None* for agents
    created programmatically.
    """

    def load_prompt(self, project_root: Path) -> str:
        if self.prompt:
            return self.prompt
        if self.prompt_path:
            return (project_root / self.prompt_path).read_text(encoding="utf-8")
        return ""

    @classmethod
    def from_db_row(cls, row: dict) -> AgentDef:
        """Reconstruct an ``AgentDef`` from a stored ``agent_versions`` row.

        Prefers the ``config_json`` column (the DB-as-source-of-truth
        snapshot); falls back to ``content_snapshot`` for legacy rows.
        Missing rows raise ``ValueError``.
        """
        import json as _json

        raw = row.get("config_json") or row.get("content_snapshot")
        if raw is None:
            raise ValueError("agent_versions row has no config payload")
        if isinstance(raw, str):
            data = _json.loads(raw)
        else:
            data = raw
        inst = cls.model_validate(data)
        # Stash the structured config_json so the agent_config
        # accessors (ExecutionConfig/RuntimeConfig/PythonAgentConfig)
        # can read execution/runtime/python sub-dicts directly without
        # roundtripping through the legacy agent.runner pydantic model.
        # Falls back to the same data dict when config_json was absent —
        # the accessors only consume sub-keys they recognize.
        try:
            inst.__dict__["_config_json"] = data
        except Exception:
            pass
        return inst


# ---------------------------------------------------------------------------
# Project-level + TOML-side shapes
# ---------------------------------------------------------------------------


class RunnerManifest(BaseModel):
    """Per-agent runner config, a subset of RunnerSpec for the TOML file.

    Workspace-generated configs (agents.json, settings.json, opencode.json)
    are resolved automatically from the workspace directory at runtime and
    do not appear here.
    """

    kind: RunnerKind = RunnerKind.TOKEN
    """Defaults to ``token`` so markdown-only agents need no
    explicit runner configuration."""

    model: str | None = None
    agent_module: str | None = None
    """Python import path for token/pydantic-ai agents
    (e.g. ``agents.company_researcher.agent:CompanyResearcherAgent``)."""

    mcp_config_path: str | None = None
    """Global MCP server configuration, resolved relative to project root."""

    allowed_tools: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = None

    output_schema_path: str | None = None
    max_validation_retries: int = 0
    max_error_retries: int = 0


class AgentManifest(BaseModel):
    """Per-agent metadata, read from ``<agents_dir>/<name>/agent.toml``."""

    id: str
    """Agent identifier (must match the directory name)."""

    description: str = ""
    prompt_path: str | None = None
    """Path inside the agent directory to the system prompt markdown.

    Resolved relative to the agent directory. When omitted, falls back to
    ``prompts/system.md`` if that file exists; otherwise no prompt is set.

    .. deprecated::
       Use ``[composition]`` instead.
    """

    composition: CompositionConfig | None = None
    """Prompt-composition recipe. When present, takes precedence."""

    workspace: str | None = None
    session_mode: SessionMode = "headless"
    webhook_url: str | None = None
    tags: list[str] = Field(default_factory=list)

    runner: RunnerManifest | None = None
    """Runner configuration. When unset, a default ``token``
    runner is used (auto-generated agent from the markdown prompt)."""


class ProjectManifest(BaseModel):
    project: str = "default"
    agents_dir: str = "agents"
    """Project-relative path to the bound agents directory.

    Agentbox scans this directory for subdirectories containing
    ``agent.toml`` files and registers each as an agent.
    """

    agents: list[AgentDef] = Field(default_factory=list)
    """Inline agent definitions (``[[agents]]`` in agentbox.toml).

    These are merged with directory-discovered agents; inline takes
    precedence when IDs collide.
    """

    workspaces: list[WorkspaceDef] = Field(default_factory=list)
    """Named workspace definitions (``[[workspaces]]`` in agentbox.toml)."""

    mcp_servers: list[McpServerSpec] = Field(default_factory=list)
    """MCP server configurations (``[[mcp_servers]]`` in agentbox.toml).

    Each entry specifies a named MCP server with its connection details.
    Tool groups are resolved at runtime by introspecting each server.
    """

    # --- Deprecated flat fields (migrate to mcp_servers) ---

    mcp_server_name: str | None = None
    """Deprecated: use ``mcp_servers`` instead."""

    mcp_command: list[str] | None = None
    """Deprecated: use ``mcp_servers`` instead."""

    mcp_url: str | None = None
    """Deprecated: use ``mcp_servers`` instead."""

    mcp_transport: McpTransport | None = None
    """Deprecated: use ``mcp_servers`` instead."""

    tool_manifest_path: str | None = None
    """Deprecated: tool manifest is now resolved at runtime via MCP introspection."""

    backend_preference: list[str] = Field(default_factory=list)
    """Ordered list of backend adapter names to try when an agent does
    not pin a backend explicitly. Empty list means fall back to the
    agent's ``runner.kind``."""

    shared_assets: dict[str, str] = Field(default_factory=dict)
    """Named shared-asset roots for ``shared://`` resolution in
    prompt composition. Keys are root names; values are project-relative
    directory paths."""

    @model_validator(mode="after")
    def _migrate_legacy_mcp(self) -> ProjectManifest:
        has_legacy = (
            self.mcp_server_name is not None
            or self.mcp_command is not None
            or self.mcp_url is not None
            or self.mcp_transport is not None
        )
        if has_legacy and not self.mcp_servers:
            name = self.mcp_server_name or "mcp"
            warnings.warn(
                f"agentbox.toml uses legacy MCP fields (mcp_server_name, etc.). "
                f"Migrate to [[mcp_servers]] block named {name!r}. "
                f"See docs/plans/02-mcp-introspection.md",
                DeprecationWarning,
                stacklevel=2,
            )
            if self.mcp_url is not None:
                self.mcp_servers = [
                    McpServerSpec(
                        name=name,
                        url=self.mcp_url,
                        transport=self.mcp_transport or "http",
                        command=None,
                    )
                ]
            else:
                self.mcp_servers = [
                    McpServerSpec(
                        name=name,
                        command=self.mcp_command or ["mcp_serve.sh"],
                    )
                ]
        self.mcp_servers = self.mcp_servers or [
            McpServerSpec(name="mcp", command=["mcp_serve.sh"])
        ]
        return self
