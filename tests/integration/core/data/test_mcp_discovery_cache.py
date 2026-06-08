"""Tests for McpDiscoveryMixin — cache_tools / get_cached_tools / invalidate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from agentbox.core.data import SessionStore


class TestCacheTools:
    def test_cache_and_retrieve(self, session_store: SessionStore) -> None:
        session_store.cache_tools("my-server", "hash1", ["tool_a", "tool_b"])
        result = session_store.get_cached_tools("my-server", "hash1")
        assert result == ["tool_a", "tool_b"]

    def test_empty_tool_list(self, session_store: SessionStore) -> None:
        session_store.cache_tools("my-server", "hash-empty", [])
        result = session_store.get_cached_tools("my-server", "hash-empty")
        assert result == []

    def test_miss_for_unknown_server(self, session_store: SessionStore) -> None:
        result = session_store.get_cached_tools("no-such-server", "abc")
        assert result is None

    def test_miss_for_different_hash(self, session_store: SessionStore) -> None:
        session_store.cache_tools("server-x", "hash-a", ["tool_1"])
        result = session_store.get_cached_tools("server-x", "hash-b")
        assert result is None

    def test_upsert_updates_existing_entry(self, session_store: SessionStore) -> None:
        session_store.cache_tools("server-y", "h1", ["old_tool"])
        session_store.cache_tools("server-y", "h1", ["new_tool"])
        result = session_store.get_cached_tools("server-y", "h1")
        assert result == ["new_tool"]


class TestTtlExpiry:
    def test_expired_entry_returns_none(self, session_store: SessionStore) -> None:
        """Entries older than TTL must return None."""
        # Freeze "now" to a moment 25 hours in the past when caching
        past = datetime.now(UTC) - timedelta(hours=25)
        with patch("agentbox.core.data.workspaces.mcp_discovery._now_utc",
                   return_value=past):
            session_store.cache_tools("server-z", "hash-old", ["stale_tool"])

        # Reading with the default 86400-s TTL — entry is 25 h old → expired
        result = session_store.get_cached_tools("server-z", "hash-old")
        assert result is None

    def test_fresh_entry_within_ttl_is_returned(self, session_store: SessionStore) -> None:
        """Entries younger than TTL must be returned."""
        session_store.cache_tools("server-fresh", "hash-fresh", ["live_tool"])
        result = session_store.get_cached_tools("server-fresh", "hash-fresh")
        assert result == ["live_tool"]

    def test_custom_ttl_zero_always_expires(self, session_store: SessionStore) -> None:
        """A TTL of 0 s means every entry is immediately stale."""
        session_store.cache_tools("server-q", "hq", ["tool_q"])
        result = session_store.get_cached_tools("server-q", "hq", ttl_seconds=0)
        assert result is None


class TestInvalidateServerCache:
    def test_invalidate_removes_all_entries_for_server(self, session_store: SessionStore) -> None:
        session_store.cache_tools("srv", "h1", ["t1"])
        session_store.cache_tools("srv", "h2", ["t2"])
        removed = session_store.invalidate_server_cache("srv")
        assert removed == 2
        assert session_store.get_cached_tools("srv", "h1") is None
        assert session_store.get_cached_tools("srv", "h2") is None

    def test_invalidate_only_affects_target_server(self, session_store: SessionStore) -> None:
        session_store.cache_tools("keep", "hk", ["keeper"])
        session_store.cache_tools("remove", "hr", ["gone"])
        session_store.invalidate_server_cache("remove")
        # Unrelated server must survive
        assert session_store.get_cached_tools("keep", "hk") == ["keeper"]

    def test_invalidate_nonexistent_returns_zero(self, session_store: SessionStore) -> None:
        removed = session_store.invalidate_server_cache("does-not-exist")
        assert removed == 0


class TestCacheHitAvoidance:
    def test_warm_cache_returns_without_re_fetching(self, session_store: SessionStore) -> None:
        """Integration: if cache is warm, get_cached_tools returns data directly."""
        tools = ["alpha", "beta", "gamma"]
        session_store.cache_tools("warm-srv", "cfg123", tools)

        # Simulate a second lookup without touching a live server
        result = session_store.get_cached_tools("warm-srv", "cfg123")
        assert result == tools
