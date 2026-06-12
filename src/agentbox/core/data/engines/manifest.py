"""Runner/engine specification models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentbox.core.constants import ConfiguredValidationMode, ValidationMode


class RunnerSpec(BaseModel):
    kind: str = "token"
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
    """DEPRECATED — legacy cosmetic field, kept only for backward
    compatibility with old TOML imports. The runtime model is owned by
    the agent's bound runner profile (``agent_runner_profiles`` →
    ``runner_profiles.model``). This field is no longer surfaced by
    the API, MCP tools, or CLI; new code must not read it. Some
    backend adapters still consult it as a last-resort fallback when
    no runner profile is bound — that path is also slated for
    removal."""

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

    output_validation_engine: ConfiguredValidationMode = ValidationMode.BOTH
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


class RunnerManifest(BaseModel):
    """Per-agent runner config, a subset of RunnerSpec for the TOML file.

    Workspace-generated configs (agents.json, settings.json, opencode.json)
    are resolved automatically from the workspace directory at runtime and
    do not appear here.
    """

    kind: str = "token"
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
