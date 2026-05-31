"""MCP tool discovery cache mixin (Plan 08).

Stores the result of ``discover_tools()`` in the SQLite DB so that
successive runs don't need to re-spawn every MCP server.  The TTL
defaults to 24 h and is configurable via the ``AGENTBOX_MCP_DISCOVERY_TTL``
environment variable.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.engine import Engine

from agentbox.core.data.schema import mcp_tool_discovery_cache

TTL_SECONDS = int(os.environ.get("AGENTBOX_MCP_DISCOVERY_TTL", "86400"))


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 string that may or may not carry timezone info."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class McpDiscoveryMixin:
    engine: Engine

    def get_cached_tools(
        self,
        server_name: str,
        config_hash: str,
        *,
        ttl_seconds: int | None = None,
    ) -> list[str] | None:
        """Return the cached tool list, or *None* if absent / expired.

        Parameters
        ----------
        server_name:
            The MCP server identifier (``name`` field in the server dict).
        config_hash:
            A hash of the server's configuration.  Different configs produce
            different cache entries so a config change forces re-discovery.
        ttl_seconds:
            Override the module-level ``TTL_SECONDS`` for this call.
        """
        effective_ttl = ttl_seconds if ttl_seconds is not None else TTL_SECONDS
        with self.engine.connect() as conn:
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
        """Upsert the tool list for *server_name* / *config_hash*."""
        now = _now_utc().isoformat()
        tools_json = json.dumps(tools)

        with self.engine.begin() as conn:
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
        """Delete all cache entries for *server_name*; return the count removed."""
        with self.engine.begin() as conn:
            result = conn.execute(
                mcp_tool_discovery_cache.delete().where(
                    mcp_tool_discovery_cache.c.server_name == server_name
                )
            )
            return result.rowcount or 0
