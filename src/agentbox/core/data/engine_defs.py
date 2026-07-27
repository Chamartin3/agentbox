"""Runner/engine specification models."""

from __future__ import annotations

from pydantic import BaseModel, Field

class RunnerSpec(BaseModel):
    # An agent's backend is no longer declared here. It is resolved by the one
    # runner resolver (bound profile → system-default → the module-level default backend);
    # RunnerSpec carries only non-backend runner settings.

    # --- Shared across all runners ---

    timeout_seconds: int = 1200
    """Run timeout in seconds. The agent's runner config is the single source
    of truth — runner profiles do not carry a timeout. A per-run override on
    ``POST /api/runs`` wins over this value."""

    extra_args: list[str] = Field(default_factory=list)
    """Extra CLI args passed verbatim (claude_code / opencode only)."""

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

    """

    # --- token direct-Agent dependencies ---

    deps_factory: str | None = None
    """Dotted import path ``module.path:callable`` that constructs the
    ``deps`` object passed to a ``pydantic_ai.Agent.run_sync(deps=...)``
    call. Resolved at run time."""

    # --- Output validation & retry ---

    output_schema_path: str | None = None

    max_validation_retries: int = 0
    max_error_retries: int = 0
    """How many times to re-run the agent when the run fails with an error
    (excluding timeouts and validation failures, which have their own retry
    configuration)."""
