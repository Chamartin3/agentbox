"""McpToolDiscoveryCacheManager — MCP discovery cache CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.mcp_discovery_cache import McpToolDiscoveryCache


class McpToolDiscoveryCacheManager(Manager[McpToolDiscoveryCache]):
    """Manager for the ``mcp_tool_discovery_cache`` table."""
    model = McpToolDiscoveryCache
