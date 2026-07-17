"""Workspace and MCP server specification models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

McpTransport = Literal["http", "sse", "stdio"]


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
