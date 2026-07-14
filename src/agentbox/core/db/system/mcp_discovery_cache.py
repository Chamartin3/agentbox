"""McpToolDiscoveryCache model + manager — cached tool manifests for MCP servers.

Maps to the ``mcp_tool_discovery_cache`` table.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.config import SETTINGS
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs
from agentbox.core.db.schema import mcp_tool_discovery_cache

TTL_SECONDS = SETTINGS.mcp_discovery_ttl


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


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


class McpToolDiscoveryCacheManager(Manager[McpToolDiscoveryCache]):
    """Manager for the ``mcp_tool_discovery_cache`` table."""

    model = McpToolDiscoveryCache

    # ── pure-DB primitives (ported from McpDiscoveryMixin) ──────────────

    def get_cached_tools(
        self,
        server_name: str,
        config_hash: str,
        *,
        ttl_seconds: int | None = None,
    ) -> list[str] | None:
        effective_ttl = ttl_seconds if ttl_seconds is not None else TTL_SECONDS
        with self._engine.connect() as conn:
            row = conn.execute(
                mcp_tool_discovery_cache.select().where(
                    (mcp_tool_discovery_cache.c.server_name == server_name)
                    & (mcp_tool_discovery_cache.c.config_hash == config_hash)
                )
            ).first()
        if row is None:
            return None
        discovered_at = _parse_iso(row.discovered_at)
        if _now_utc() - discovered_at > timedelta(seconds=effective_ttl):
            return None
        tools: list[str] = json.loads(row.tools_json)
        return tools

    def cache_tools(
        self,
        server_name: str,
        config_hash: str,
        tools: list[str],
    ) -> None:
        now = _now_utc().isoformat()
        tools_json = json.dumps(tools)
        with self._engine.begin() as conn:
            existing = conn.execute(
                mcp_tool_discovery_cache.select().where(
                    (mcp_tool_discovery_cache.c.server_name == server_name)
                    & (mcp_tool_discovery_cache.c.config_hash == config_hash)
                )
            ).first()
            if existing:
                conn.execute(
                    mcp_tool_discovery_cache.update()
                    .where(mcp_tool_discovery_cache.c.id == existing.id)
                    .values(tools_json=tools_json, discovered_at=now)
                )
            else:
                conn.execute(
                    mcp_tool_discovery_cache.insert().values(
                        id=uuid.uuid4().hex,
                        server_name=server_name,
                        config_hash=config_hash,
                        tools_json=tools_json,
                        discovered_at=now,
                    )
                )

    def invalidate_server_cache(self, server_name: str) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                mcp_tool_discovery_cache.delete().where(
                    mcp_tool_discovery_cache.c.server_name == server_name
                )
            )
            return result.rowcount or 0
