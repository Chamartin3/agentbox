"""McpToolDiscoveryCache model — cached tool manifests for MCP servers.

Maps to the ``mcp_tool_discovery_cache`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity


class McpToolDiscoveryCache(Entity, table=True):
    """Cached tool manifest for an MCP server identified by its config hash."""

    __tablename__ = tablename("mcp_tool_discovery_cache")

    id: str = Field(primary_key=True)
    server_name: str = Field(nullable=False)
    config_hash: str = Field(nullable=False)
    tools_json: str = Field(nullable=False)
    discovered_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        UniqueConstraint("server_name", "config_hash", name="uq_mcp_discovery_server_hash"),
        Index("ix_mcp_discovery_server", "server_name"),
    )
