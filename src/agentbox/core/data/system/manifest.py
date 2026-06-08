"""Project-level manifest model (agentbox.toml top-level)."""

from __future__ import annotations

import warnings

from pydantic import BaseModel, Field, model_validator

from agentbox.core.data.agents.manifest import AgentDef
from agentbox.core.data.workspaces.manifest import McpServerSpec, McpTransport, WorkspaceDef


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
