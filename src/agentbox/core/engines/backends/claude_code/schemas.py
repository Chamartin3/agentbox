"""Pydantic models for Claude Code configuration files.

Covers every JSON artifact that agentbox generates or ships as a default:
  - claude_agents.json   (sub-agent definitions passed via --agents)
  - claude_settings.json (workspace permissions, passed via --settings)
  - claude_mcp.json      (MCP server wiring, passed via --mcp-config)
  - user-config.json     (UI preferences seeded into the creds volume)

Pinned to Claude Code 2.1.111.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

# ---------------------------------------------------------------------------
# claude_agents.json
# ---------------------------------------------------------------------------


class ClaudeAgentEntry(BaseModel):
    """One entry in the claude_agents.json agents map."""

    description: str = ""
    prompt: str = ""
    allowedTools: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class ClaudeAgentsConfig(RootModel[dict[str, ClaudeAgentEntry]]):
    """Top-level shape of claude_agents.json: {agent_name: ClaudeAgentEntry}."""

    root: dict[str, ClaudeAgentEntry] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# claude_settings.json
# ---------------------------------------------------------------------------


class ClaudePermissions(BaseModel):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)


class ClaudeSettingsConfig(BaseModel):
    """Workspace settings.json — permissions block + optional extras."""

    permissions: ClaudePermissions = Field(default_factory=ClaudePermissions)
    theme: Literal["dark", "light"] | None = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# claude_mcp.json
# ---------------------------------------------------------------------------


class ClaudeMcpServerHttp(BaseModel):
    """Remote MCP server entry (http or sse transport)."""

    type: Literal["http", "sse"]
    url: str


class ClaudeMcpServerStdio(BaseModel):
    """Local MCP server entry (stdio transport)."""

    command: str
    args: list[str] = Field(default_factory=list)


ClaudeMcpServerEntry = Annotated[
    ClaudeMcpServerHttp | ClaudeMcpServerStdio,
    Field(discriminator=None),
]


class ClaudeMcpConfig(BaseModel):
    """Top-level shape of claude_mcp.json."""

    mcpServers: dict[str, ClaudeMcpServerHttp | ClaudeMcpServerStdio] = Field(
        default_factory=dict
    )

    model_config = {"extra": "allow"}

    # Empty mcpServers is allowed: a workspace with deny_all_unless_enabled
    # policy and no enabled servers should still produce a valid config.


# ---------------------------------------------------------------------------
# user-config.json (seeded into the agentbox-claude volume)
# ---------------------------------------------------------------------------


class ClaudeUserConfig(BaseModel):
    """Claude Code UI preferences written to the credentials volume.

    These are user-level settings (theme, onboarding state) not runner config.
    Pinned to Claude Code 2.1.111.
    """

    theme: Literal["dark", "light"] = "dark"
    hasCompletedOnboarding: bool = True
    bypassPermissionsModeAccepted: bool = True
    hasSeenTasksHint: bool = True
    hasAcknowledgedCostThreshold: bool = True
    verbose: bool = False

    model_config = {"extra": "allow"}
