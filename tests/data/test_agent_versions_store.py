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


# ------------------------------------------------------------------
# Agent lifecycle tests (create_agent, publish_version, branch_draft, rollback_to)
# ------------------------------------------------------------------


class TestAgentLifecycle:
    def test_create_agent_writes_draft_v1_and_meta(self, session_store) -> None:
        config = {"id": "my-agent", "runner": "claude"}
        v = session_store.create_agent(
            agent_id="my-agent",
            config_json=config,
            prompt_content="Be helpful.",
            author="test-user",
            changelog="Initial version",
            source="ui",
            source_path="/tmp/agent.toml",
            source_format="toml",
            sync_mode="watch",
            export_to_disk=True,
        )
        assert v["version"] == 1
        assert v["agent_id"] == "my-agent"
        assert v["is_draft"] == 1
        assert v["author"] == "test-user"
        assert v["config_json"] is not None
        assert v["prompt_content"] == "Be helpful."
        assert v["source"] == "ui"
        assert v["changelog"] == "Initial version"

        # Verify agent_meta row exists
        meta = session_store.get_agent_meta("my-agent")
        assert meta is not None
        assert meta["sync_mode"] == "watch"
        assert meta["export_to_disk"] == 1

    def test_create_agent_rejects_duplicate_id(self, session_store) -> None:
        session_store.create_agent(
            agent_id="duplicate",
            config_json={"id": "duplicate"},
            author="user",
            changelog="v1",
        )
        with pytest.raises(ValueError, match="already exists"):
            session_store.create_agent(
                agent_id="duplicate",
                config_json={"id": "duplicate"},
                author="user",
                changelog="v2",
            )

    def test_create_agent_updates_orphaned_meta(self, session_store) -> None:
        # Manually insert an orphaned meta row
        session_store.init_agent_meta(
            "orphan-agent", sync_mode="manual", export_to_disk=False
        )

        # Now create_agent should update it
        session_store.create_agent(
            agent_id="orphan-agent",
            config_json={"id": "orphan-agent"},
            author="user",
            changelog="v1",
            sync_mode="watch",
            export_to_disk=True,
        )

        meta = session_store.get_agent_meta("orphan-agent")
        assert meta["sync_mode"] == "watch"
        assert meta["export_to_disk"] == 1

    def test_publish_flips_draft_and_sets_active(self, session_store) -> None:
        v1 = session_store.create_agent(
            agent_id="pub-agent",
            config_json={"id": "pub-agent"},
            author="user",
            changelog="initial",
        )
        assert v1["is_draft"] == 1

        published = session_store.publish_version("pub-agent", 1, "Ready for use")
        assert published["is_draft"] == 0
        assert "publish: Ready for use" in published["changelog"]

        # Verify active pointer
        active = session_store.get_active_version("pub-agent")
        assert active is not None
        assert active["version"] == 1

    def test_publish_appends_to_existing_changelog(self, session_store) -> None:
        session_store.create_agent(
            agent_id="changelog-agent",
            config_json={"id": "changelog-agent"},
            author="user",
            changelog="Initial changelog",
        )
        published = session_store.publish_version("changelog-agent", 1, "Now ready")
        assert "Initial changelog" in published["changelog"]
        assert "publish: Now ready" in published["changelog"]

    def test_publish_rejects_short_reason(self, session_store) -> None:
        session_store.create_agent(
            agent_id="short-reason",
            config_json={"id": "short-reason"},
            author="user",
            changelog="v1",
        )
        with pytest.raises(ValueError, match="at least 3 characters"):
            session_store.publish_version("short-reason", 1, "hi")
        with pytest.raises(ValueError, match="at least 3 characters"):
            session_store.publish_version("short-reason", 1, "")

    def test_publish_is_idempotent_for_already_active(self, session_store) -> None:
        session_store.create_agent(
            agent_id="idempotent",
            config_json={"id": "idempotent"},
            author="user",
            changelog="v1",
        )
        session_store.publish_version("idempotent", 1, "First")
        first_active = session_store.get_active_version("idempotent")

        # Publish again
        session_store.publish_version("idempotent", 1, "Second")
        second_active = session_store.get_active_version("idempotent")

        # Should still point to v1; changelog updated
        assert first_active["version"] == 1
        assert second_active["version"] == 1
        assert "Second" in second_active["changelog"]

    def test_publish_raises_for_missing_version(self, session_store) -> None:
        session_store.create_agent(
            agent_id="missing-pub",
            config_json={"id": "missing-pub"},
            author="user",
            changelog="v1",
        )
        with pytest.raises(ValueError, match="not found"):
            session_store.publish_version("missing-pub", 99, "publish")

    def test_branch_draft_copies_config_and_files(self, session_store) -> None:
        # Create v1, publish, and add a file
        v1 = session_store.create_agent(
            agent_id="branch-agent",
            config_json={"id": "branch-agent", "version": 1},
            prompt_content="Original prompt",
            author="user",
            changelog="v1",
        )
        session_store.publish_version("branch-agent", 1, "Publish")

        # Add a file to v1
        session_store.insert_version_files(
            v1["id"],
            [
                {
                    "relative_path": "prompt.md",
                    "kind": "system",
                    "content": "System prompt",
                }
            ],
        )

        # Branch into draft v2
        v2 = session_store.branch_draft("branch-agent", author="brancher")
        assert v2["version"] == 2
        assert v2["is_draft"] == 1
        assert v2["author"] == "brancher"
        assert v2["config_json"] == v1["config_json"]
        assert v2["prompt_content"] == v1["prompt_content"]
        assert "branched from v1" in v2["changelog"]

        # Verify files copied
        v1_files = session_store.list_version_files(v1["id"])
        v2_files = session_store.list_version_files(v2["id"])
        assert len(v2_files) == len(v1_files)
        assert v2_files[0]["relative_path"] == "prompt.md"
        assert v2_files[0]["content"] == "System prompt"

    def test_branch_draft_raises_without_active_version(self, session_store) -> None:
        session_store.create_agent(
            agent_id="no-active",
            config_json={"id": "no-active"},
            author="user",
            changelog="v1",
        )
        # v1 is draft, no active version set
        with pytest.raises(ValueError, match="No active version"):
            session_store.branch_draft("no-active", author="user")

    def test_branch_draft_does_not_change_active_pointer(self, session_store) -> None:
        session_store.create_agent(
            agent_id="multi-draft",
            config_json={"id": "multi-draft"},
            author="user",
            changelog="v1",
        )
        session_store.publish_version("multi-draft", 1, "Pub")

        active_before = session_store.get_active_version("multi-draft")
        session_store.branch_draft("multi-draft", author="user")
        active_after = session_store.get_active_version("multi-draft")

        assert active_before["version"] == active_after["version"]
        assert active_after["version"] == 1

    def test_rollback_creates_new_version_and_activates_it(self, session_store) -> None:
        # Create v1, publish
        v1 = session_store.create_agent(
            agent_id="rollback-agent",
            config_json={"id": "rollback-agent", "value": 1},
            author="user",
            changelog="v1",
        )
        session_store.publish_version("rollback-agent", 1, "Publish v1")

        # Create v2 (different config), publish
        v2_dict = session_store.create_version(
            agent_id="rollback-agent",
            source_path="/tmp/test.md",
            source_format="markdown",
            content_snapshot='{"id": "rollback-agent", "value": 2}',
            prompt_snapshot="Updated prompt",
            content_hash="def456",
            author="user",
            changelog="v2 changes",
            config_json='{"id": "rollback-agent", "value": 2}',
            prompt_content="Updated",
            is_draft=False,
        )
        session_store.activate_version("rollback-agent", v2_dict["id"])

        # Rollback to v1
        v3 = session_store.rollback_to(
            "rollback-agent", 1, "Config too risky", author="operator"
        )

        assert v3["version"] == 3
        assert v3["is_draft"] == 0
        assert v3["author"] == "operator"
        assert v3["config_json"] == v1["config_json"]
        assert "rollback to v1: Config too risky" in v3["changelog"]

        # Verify active pointer
        active = session_store.get_active_version("rollback-agent")
        assert active["version"] == 3

    def test_rollback_copies_files_from_target(self, session_store) -> None:
        v1 = session_store.create_agent(
            agent_id="rollback-files",
            config_json={"id": "rollback-files"},
            author="user",
            changelog="v1",
        )
        session_store.publish_version("rollback-files", 1, "Pub")

        # Add file to v1
        session_store.insert_version_files(
            v1["id"],
            [
                {
                    "relative_path": "config.json",
                    "kind": "output_schema",
                    "content": '{"type": "object"}',
                }
            ],
        )

        # Create and publish v2
        v2 = session_store.create_version(
            agent_id="rollback-files",
            source_path="/tmp/test.md",
            source_format="markdown",
            content_snapshot='{"id": "rollback-files"}',
            prompt_snapshot="v2",
            content_hash="xyz",
            author="user",
            is_draft=False,
        )
        session_store.activate_version("rollback-files", v2["id"])

        # Rollback to v1
        v3 = session_store.rollback_to(
            "rollback-files", 1, "Revert config", author="user"
        )

        # v3 should have v1's files
        v3_files = session_store.list_version_files(v3["id"])
        assert len(v3_files) == 1
        assert v3_files[0]["relative_path"] == "config.json"
        assert v3_files[0]["content"] == '{"type": "object"}'

    def test_rollback_rejects_short_reason(self, session_store) -> None:
        session_store.create_agent(
            agent_id="rollback-reason",
            config_json={"id": "rollback-reason"},
            author="user",
            changelog="v1",
        )
        session_store.publish_version("rollback-reason", 1, "Pub")

        with pytest.raises(ValueError, match="at least 3 characters"):
            session_store.rollback_to("rollback-reason", 1, "no", author="user")

    def test_rollback_raises_for_missing_target_version(self, session_store) -> None:
        session_store.create_agent(
            agent_id="rollback-missing",
            config_json={"id": "rollback-missing"},
            author="user",
            changelog="v1",
        )
        session_store.publish_version("rollback-missing", 1, "Pub")

        with pytest.raises(ValueError, match="not found"):
            session_store.rollback_to("rollback-missing", 99, "Rollback", author="user")
