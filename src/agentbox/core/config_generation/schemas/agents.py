"""Pydantic schemas for agent definition files.

Agents can be defined in two ways:
  1. TOML blocks inside agentbox.toml (parsed by core/data/manifest.py)
  2. Markdown files with YAML frontmatter in agents.d/

This module covers the markdown frontmatter schema and the runner-native
agent definition formats that each runner writes into its workspace:
  - ClaudeAgentMarkdown   → agents.d/<id>.md frontmatter (runner: claude_code)
  - OpenCodeAgentMarkdown → agents.d/<id>.md frontmatter (runner: opencode)

Both share AgentMarkdownBase for common fields.

Claude Code agent markdown format:
  ---
  id: my-agent
  description: What the agent does
  model: claude-sonnet-4-6
  tools:
    - Read
    - mcp__my-mcp__tool_name
    - @group.read
  runner:
    kind: claude_code
    timeout_seconds: 180
  ---
  System prompt body...

OpenCode agent markdown format:
  ---
  id: my-agent
  description: What the agent does
  model: anthropic/claude-sonnet-4-6
  runner:
    kind: opencode
    timeout_seconds: 180
  ---
  System prompt body...
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ._model_registry import CLAUDE_MODELS, OPENCODE_MODELS

# ---------------------------------------------------------------------------
# Shared runner config block
# ---------------------------------------------------------------------------


class RunnerBlock(BaseModel):
    """Inline runner config inside a markdown frontmatter block."""

    kind: Literal[
        "claude_code", "opencode", "pydantic_ai", "http", "subprocess", "adapter"
    ] = "pydantic_ai"
    timeout_seconds: int = Field(default=120, ge=1)
    mcp_config_path: str | None = None
    agents_config_path: str | None = None
    settings_path: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)
    agent_module: str | None = None
    output_schema_path: str | None = None
    max_validation_retries: int = Field(default=0, ge=0)

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------


class AgentMarkdownBase(BaseModel):
    """Fields shared by all agent markdown frontmatter variants."""

    id: str = Field(description="Unique agent identifier (slug, no spaces).")
    description: str | None = None
    workspace: str | None = None
    session_mode: Literal["headless", "persistent"] = "headless"
    headless: bool = False
    webhook_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    unsupported_backends: list[str] = Field(default_factory=list)
    prompt: str | None = None
    prompt_path: str | None = None
    runner: RunnerBlock = Field(default_factory=RunnerBlock)

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Claude Code agent markdown
# ---------------------------------------------------------------------------


class ClaudeAgentMarkdown(AgentMarkdownBase):
    """Frontmatter for a Claude Code agent defined in agents.d/<id>.md.

    The ``model`` field must be a known Claude model ID or short alias.
    Run ``scripts/fetch_models.py`` to refresh the registry.
    """

    model: str | None = Field(
        default=None,
        description=(
            "Claude model ID or short alias (e.g. 'claude-sonnet-4-6', 'sonnet'). "
            "None uses the runner default."
        ),
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Tool names, @group refs, or mcp__ prefixed MCP tools.",
    )
    claude_agent: bool = True

    @field_validator("model")
    @classmethod
    def _validate_model(cls, v: str | None) -> str | None:
        if v is not None and v not in CLAUDE_MODELS:
            known = ", ".join(sorted(CLAUDE_MODELS))
            raise ValueError(
                f"Unknown Claude model {v!r}. Known models: {known}. "
                "Run scripts/fetch_models.py to update the registry."
            )
        return v


# ---------------------------------------------------------------------------
# OpenCode agent markdown
# ---------------------------------------------------------------------------


class OpenCodeAgentMarkdown(AgentMarkdownBase):
    """Frontmatter for an OpenCode agent defined in agents.d/<id>.md.

    The ``model`` field must be a known OpenCode model string
    (``provider/model-id`` notation).
    Run ``scripts/fetch_models.py`` to refresh the registry.
    """

    model: str | None = Field(
        default=None,
        description=(
            "OpenCode model string, e.g. 'anthropic/claude-sonnet-4-6' or "
            "'openai/gpt-4o'. None uses the OpenCode default."
        ),
    )

    @field_validator("model")
    @classmethod
    def _validate_model(cls, v: str | None) -> str | None:
        if v is not None and v not in OPENCODE_MODELS:
            known = ", ".join(sorted(OPENCODE_MODELS))
            raise ValueError(
                f"Unknown OpenCode model {v!r}. Known models: {known}. "
                "Run scripts/fetch_models.py to update the registry."
            )
        return v
