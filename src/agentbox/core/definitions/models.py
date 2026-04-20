"""Declarative agent definitions loaded from the project volume."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agentbox.core.constants import RunnerKind, SessionMode


class RunnerSpec(BaseModel):
    kind: RunnerKind
    """Which Runner plugin to dispatch to."""

    # --- Shared across all runners ---

    timeout_seconds: int = 120

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

    # --- pydantic_ai runner ---

    agent_module: str | None = None
    """Python import path to the pydantic-ai Agent class.

    Format: ``module.path:ClassName`` (e.g.
    ``agents.company_researcher.agent:CompanyResearcherAgent``).

    When unset but ``prompt_path`` is provided on the ``AgentDef``,
    a minimal agent is auto-generated from the markdown.
    """

    # --- Output validation & retry ---

    output_schema_path: str | None = None
    """Project-relative path to a JSON Schema file for output validation.

    When set, the executor validates the agent's output against this
    schema after each run attempt. If validation fails, the agent is
    re-run with the validation error in the prompt (up to
    ``max_validation_retries`` times).
    """

    max_validation_retries: int = 0
    """How many times to re-run the agent when output fails schema validation."""


class GuardrailRef(BaseModel):
    name: str
    """Entrypoint name registered under `agentbox.guardrails`."""

    options: dict = Field(default_factory=dict)


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
    """Path to permissions file relative to workspace."""


class AgentDef(BaseModel):
    id: str
    """Stable identifier (e.g. `myproject.draft_writer`)."""

    description: str = ""
    prompt_path: str | None = None
    """Project-relative path to system prompt markdown.

    For ``pydantic_ai`` runners without an explicit ``agent_module``,
    this markdown is used to auto-generate a minimal agent.
    """

    prompt: str | None = None
    """Inline system prompt text. Mutually exclusive with ``prompt_path`` —
    when both are set, ``prompt`` wins."""

    workspace: str | None = None
    """Workspace reference.

    Resolution:
    - Named workspace: "default", "research" (looked up in workspaces table)
    - Explicit path: "workdir/agentbox/ws/foo"
    - "<ephemeral>": fresh tmp dir per run, deleted after (sandbox mode).
    - Omitted: auto-resolved to ``<workspaces_root>/<agent_id>/``.
    """

    runner: RunnerSpec
    session_mode: SessionMode = "headless"
    guardrails: list[GuardrailRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

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

    def load_prompt(self, project_root: Path) -> str:
        if self.prompt:
            return self.prompt
        if self.prompt_path:
            return (project_root / self.prompt_path).read_text(encoding="utf-8")
        return ""


class ProjectManifest(BaseModel):
    project: str = "default"
    workspaces: list[WorkspaceDef] = Field(default_factory=list)
    agents: list[AgentDef] = Field(default_factory=list)
