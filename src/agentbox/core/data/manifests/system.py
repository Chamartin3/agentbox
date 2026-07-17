"""Project-level manifest model (agentbox.toml top-level)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from agentbox.core.data.manifests.agents import AgentDef
from agentbox.core.data.manifests.workspaces import McpServerSpec, WorkspaceDef


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

    backend_preference: list[str] = Field(default_factory=list)
    """Ordered list of backend adapter names to try when an agent does
    not pin a backend explicitly. Empty list means fall back to the
    agent's ``runner.kind``."""

    shared_assets: dict[str, str] = Field(default_factory=dict)
    """Named shared-asset roots for ``shared://`` resolution in
    prompt composition. Keys are root names; values are project-relative
    directory paths."""

    @model_validator(mode="after")
    def _default_mcp_servers(self) -> ProjectManifest:
        self.mcp_servers = self.mcp_servers or [
            McpServerSpec(name="mcp", command=["mcp_serve.sh"])
        ]
        return self
