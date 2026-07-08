"""MCP machinery — generic, knows no server by name.

state → registry.py · wire → transport.py · vocabulary → manifest.py
"""

from agentbox.core.workspaces.tooling.mcp.manifest import (
    McpToolManifest as McpToolManifest,
    Tool as Tool,
    derive_groups as derive_groups,
    resolve_group_ref as resolve_group_ref,
)
from agentbox.core.workspaces.tooling.mcp.registry import (
    McpHealthReport as McpHealthReport,
    McpRegistry as McpRegistry,
    ServerHealth as ServerHealth,
    ServerStatus as ServerStatus,
)
from agentbox.core.workspaces.tooling.mcp.transport import McpClient as McpClient

__all__ = [
    "McpClient",
    "McpHealthReport",
    "McpRegistry",
    "McpToolManifest",
    "ServerHealth",
    "ServerStatus",
    "Tool",
    "derive_groups",
    "resolve_group_ref",
]
