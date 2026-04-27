"""Tests for AgentVersionsMixin — CRUD, diff, comments, ratings."""

from __future__ import annotations

import pytest


def _build_version(
    store,
    agent_id: str = "test-agent",
    version: int = 1,
    author: str = "system",
    changelog: str = "",
    is_legacy: bool = False,
) -> dict:
    return store.create_version(
        agent_id=agent_id,
        source_path="/tmp/test.md",
        source_format="markdown",
        content_snapshot='{"id": "test-agent"}',
        prompt_snapshot="Be helpful.",
        content_hash="abc123",
        author=author,
        changelog=changelog,
        is_legacy=is_legacy,
    )


class TestAgentVersionsMixin:
    def test_create_version(self, session_store) -> None:
        v = _build_version(session_store)
        assert v["version"] == 1
        assert v["agent_id"] == "test-agent"
        assert v["author"] == "system"
        assert v["source_format"] == "markdown"

    def test_latest_version_returns_newest(self, session_store) -> None:
        _build_version(session_store, author="v1")
        _build_version(session_store, author="v2", changelog="update")
        latest = session_store.latest_version("test-agent")
        assert latest is not None
        assert latest["version"] == 2
        assert latest["author"] == "v2"

    def test_latest_version_returns_none_for_missing(self, session_store) -> None:
        assert session_store.latest_version("missing") is None

    def test_get_version(self, session_store) -> None:
        _build_version(session_store)
        v = session_store.get_version("test-agent", 1)
        assert v is not None
        assert v["version"] == 1

    def test_get_version_returns_none_for_missing(self, session_store) -> None:
        assert session_store.get_version("test-agent", 99) is None

    def test_list_agents_with_latest_returns_one_row_per_agent(
        self, session_store
    ) -> None:
        _build_version(session_store, agent_id="a")
        _build_version(session_store, agent_id="a", author="v2")
        _build_version(session_store, agent_id="b")
        rows = session_store.list_agents_with_latest()
        by_id = {r["agent_id"]: r for r in rows}
        assert set(by_id) == {"a", "b"}
        assert by_id["a"]["version"] == 2
        assert by_id["b"]["version"] == 1

    def test_list_agents_with_latest_empty(self, session_store) -> None:
        assert session_store.list_agents_with_latest() == []

    def test_list_versions_ordered_desc(self, session_store) -> None:
        _build_version(session_store, author="first")
        _build_version(session_store, author="second")
        versions = session_store.list_versions("test-agent")
        assert len(versions) == 2
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

    def test_list_versions_empty(self, session_store) -> None:
        assert session_store.list_versions("missing") == []

    def test_diff_versions(self, session_store) -> None:
        session_store.create_version(
            agent_id="diff-agent",
            source_path="/tmp/test.md",
            source_format="markdown",
            content_snapshot='{"id": "old"}',
            prompt_snapshot="Old prompt",
            content_hash="aaa",
            author="system",
        )
        session_store.create_version(
            agent_id="diff-agent",
            source_path="/tmp/test.md",
            source_format="markdown",
            content_snapshot='{"id": "new", "extra": true}',
            prompt_snapshot="New prompt",
            content_hash="bbb",
            author="system",
        )
        diff = session_store.diff_versions("diff-agent", 1, 2)
        assert diff["from_version"] == 1
        assert diff["to_version"] == 2
        assert "New prompt" in diff["prompt_diff"]
        assert diff["content_diff"]["added"] == {"extra": True}

    def test_diff_versions_raises_on_missing(self, session_store) -> None:
        _build_version(session_store)
        with pytest.raises(ValueError, match="version not found"):
            session_store.diff_versions("test-agent", 1, 99)

    def test_add_and_list_comments(self, session_store) -> None:
        v = _build_version(session_store)
        session_store.add_comment(v["id"], "user1", "Looks good")
        session_store.add_comment(v["id"], "user2", "Needs work")
        comments = session_store.list_comments(v["id"])
        assert len(comments) == 2
        assert comments[0]["author"] == "user1"
        assert comments[1]["author"] == "user2"

    def test_set_and_get_rating(self, session_store) -> None:
        v = _build_version(session_store)
        session_store.set_rating(v["id"], 4, "reviewer")
        rating = session_store.get_rating(v["id"])
        assert rating is not None
        assert rating["rating"] == 4
        assert rating["rater"] == "reviewer"

    def test_rating_clamped(self, session_store) -> None:
        v = _build_version(session_store)
        with pytest.raises(ValueError, match="rating must be 1-5"):
            session_store.set_rating(v["id"], 6, "reviewer")

    def test_get_rating_returns_none(self, session_store) -> None:
        assert session_store.get_rating(999) is None

    def test_is_legacy_flag(self, session_store) -> None:
        _build_version(session_store, is_legacy=True)
        v = session_store.latest_version("test-agent")
        assert v is not None
        assert v["is_legacy"] is True

    def test_multiple_agents_isolated(self, session_store) -> None:
        _build_version(session_store, agent_id="agent-a")
        _build_version(session_store, agent_id="agent-b")
        assert len(session_store.list_versions("agent-a")) == 1
        assert len(session_store.list_versions("agent-b")) == 1
