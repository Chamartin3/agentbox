"""Tests for AgentVersionsMixin — CRUD, diff, comments, ratings."""

from __future__ import annotations

import pytest

from agentbox.core.data import AgentVersionRow
from agentbox.core.db.database import Database
from agentbox.core.service.agents import AgentService


@pytest.fixture
def svc(db: Database) -> AgentService:
    return AgentService()


def _build_version(
    store: AgentService,
    agent_id: str = "test-agent",
    version: int = 1,
    author: str = "system",
    changelog: str = "",
    is_legacy: bool = False,
) -> AgentVersionRow:
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
    def test_create_version(self, svc: AgentService) -> None:
        v = _build_version(svc)
        assert v["version"] == 1
        assert v["agent_id"] == "test-agent"
        assert v["author"] == "system"
        assert v["source_format"] == "markdown"

    def test_latest_version_returns_newest(self, svc: AgentService) -> None:
        _build_version(svc, author="v1")
        _build_version(svc, author="v2", changelog="update")
        latest = svc.latest_version("test-agent")
        assert latest is not None
        assert latest["version"] == 2
        assert latest["author"] == "v2"

    def test_latest_version_returns_none_for_missing(self, svc: AgentService) -> None:
        assert svc.latest_version("missing") is None

    def test_get_version(self, svc: AgentService) -> None:
        _build_version(svc)
        v = svc.get_version("test-agent", 1)
        assert v is not None
        assert v["version"] == 1

    def test_get_version_returns_none_for_missing(self, svc: AgentService) -> None:
        assert svc.get_version("test-agent", 99) is None

    def test_list_agents_with_latest_returns_one_row_per_agent(
        self, svc: AgentService
    ) -> None:
        _build_version(svc, agent_id="a")
        _build_version(svc, agent_id="a", author="v2")
        _build_version(svc, agent_id="b")
        rows = svc.list_agents_with_latest()
        by_id = {r["agent_id"]: r for r in rows}
        assert set(by_id) == {"a", "b"}
        assert by_id["a"]["version"] == 2
        assert by_id["b"]["version"] == 1

    def test_list_agents_with_latest_empty(self, svc: AgentService) -> None:
        assert svc.list_agents_with_latest() == []

    def test_list_versions_ordered_desc(self, svc: AgentService) -> None:
        _build_version(svc, author="first")
        _build_version(svc, author="second")
        versions = svc.list_versions("test-agent")
        assert len(versions) == 2
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

    def test_list_versions_empty(self, svc: AgentService) -> None:
        assert svc.list_versions("missing") == []

    def test_diff_versions(self, svc: AgentService) -> None:
        svc.create_version(
            agent_id="diff-agent",
            source_path="/tmp/test.md",
            source_format="markdown",
            content_snapshot='{"id": "old"}',
            prompt_snapshot="Old prompt",
            content_hash="aaa",
            author="system",
        )
        svc.create_version(
            agent_id="diff-agent",
            source_path="/tmp/test.md",
            source_format="markdown",
            content_snapshot='{"id": "new", "extra": true}',
            prompt_snapshot="New prompt",
            content_hash="bbb",
            author="system",
        )
        diff = svc.diff_versions("diff-agent", 1, 2)
        assert diff["from_version"] == 1
        assert diff["to_version"] == 2
        assert "New prompt" in diff["prompt_diff"]
        assert diff["content_diff"]["added"] == {"extra": True}

    def test_diff_versions_raises_on_missing(self, svc: AgentService) -> None:
        _build_version(svc)
        with pytest.raises(ValueError, match="version not found"):
            svc.diff_versions("test-agent", 1, 99)

    def test_add_and_list_comments(self, svc: AgentService) -> None:
        v = _build_version(svc)
        svc.add_comment(v["id"], "user1", "Looks good")
        svc.add_comment(v["id"], "user2", "Needs work")
        comments = svc.list_comments(v["id"])
        assert len(comments) == 2
        assert comments[0]["author"] == "user1"
        assert comments[1]["author"] == "user2"

    def test_set_and_get_rating(self, svc: AgentService) -> None:
        v = _build_version(svc)
        svc.set_rating(v["id"], 4, "reviewer")
        rating = svc.get_rating(v["id"])
        assert rating is not None
        assert rating["rating"] == 4
        assert rating["rater"] == "reviewer"

    def test_rating_clamped(self, svc: AgentService) -> None:
        v = _build_version(svc)
        with pytest.raises(ValueError, match="rating must be 1-5"):
            svc.set_rating(v["id"], 6, "reviewer")

    def test_get_rating_returns_none(self, svc: AgentService) -> None:
        assert svc.get_rating(999) is None

    def test_is_legacy_flag(self, svc: AgentService) -> None:
        _build_version(svc, is_legacy=True)
        v = svc.latest_version("test-agent")
        assert v is not None
        assert v["is_legacy"] is True

    def test_multiple_agents_isolated(self, svc: AgentService) -> None:
        _build_version(svc, agent_id="agent-a")
        _build_version(svc, agent_id="agent-b")
        assert len(svc.list_versions("agent-a")) == 1
        assert len(svc.list_versions("agent-b")) == 1


# ------------------------------------------------------------------
# Agent lifecycle tests (create_agent, publish_version, branch_draft, rollback_to)
# ------------------------------------------------------------------


class TestAgentLifecycle:
    def test_create_agent_writes_draft_v1_and_meta(self, svc: AgentService) -> None:
        config = {"id": "my-agent", "runner": "claude"}
        v = svc.create_agent(
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
        assert v["author"] == "test-user"
        assert v["config_json"] is not None
        assert v["prompt_content"] == "Be helpful."
        assert v["source"] == "ui"
        assert v["changelog"] == "Initial version"

        # Verify agent_meta row exists
        meta = svc.get_meta("my-agent")
        assert meta is not None
        assert meta["sync_mode"] == "watch"
        assert meta["export_to_disk"] == 1

    def test_create_agent_rejects_duplicate_id(self, svc: AgentService) -> None:
        svc.create_agent(
            agent_id="duplicate",
            config_json={"id": "duplicate"},
            author="user",
            changelog="v1",
        )
        with pytest.raises(ValueError, match="already exists"):
            svc.create_agent(
                agent_id="duplicate",
                config_json={"id": "duplicate"},
                author="user",
                changelog="v2",
            )

    def test_create_agent_updates_orphaned_meta(self, svc: AgentService, db: Database) -> None:
        # Manually insert an orphaned meta row via the agent_meta manager
        from agentbox.core.data import now_iso

        db.agent_meta.insert(
            agent_id="orphan-agent",
            sync_mode="manual",
            export_to_disk=0,
            created_at=now_iso(),
            updated_at=now_iso(),
        )

        # Now create_agent should update it
        svc.create_agent(
            agent_id="orphan-agent",
            config_json={"id": "orphan-agent"},
            author="user",
            changelog="v1",
            sync_mode="watch",
            export_to_disk=True,
        )

        meta = svc.get_meta("orphan-agent")
        assert meta is not None
        assert meta["sync_mode"] == "watch"
        assert meta["export_to_disk"] == 1

    def test_publish_flips_draft_and_sets_active(self, svc: AgentService) -> None:
        svc.create_agent(
            agent_id="pub-agent",
            config_json={"id": "pub-agent"},
            author="user",
            changelog="initial",
        )

        published = svc.publish_version("pub-agent", 1, "Ready for use")
        assert "publish: Ready for use" in published["changelog"]

        # Verify active pointer
        active = svc.active_version("pub-agent")
        assert active is not None
        assert active["version"] == 1

    def test_publish_appends_to_existing_changelog(self, svc: AgentService) -> None:
        svc.create_agent(
            agent_id="changelog-agent",
            config_json={"id": "changelog-agent"},
            author="user",
            changelog="Initial changelog",
        )
        published = svc.publish_version("changelog-agent", 1, "Now ready")
        assert "Initial changelog" in published["changelog"]
        assert "publish: Now ready" in published["changelog"]

    def test_publish_rejects_short_reason(self, svc) -> None:
        svc.create_agent(
            agent_id="short-reason",
            config_json={"id": "short-reason"},
            author="user",
            changelog="v1",
        )
        with pytest.raises(ValueError, match="at least 3 characters"):
            svc.publish_version("short-reason", 1, "hi")
        with pytest.raises(ValueError, match="at least 3 characters"):
            svc.publish_version("short-reason", 1, "")

    def test_publish_is_idempotent_for_already_active(self, svc) -> None:
        svc.create_agent(
            agent_id="idempotent",
            config_json={"id": "idempotent"},
            author="user",
            changelog="v1",
        )
        svc.publish_version("idempotent", 1, "First")
        first_active = svc.active_version("idempotent")

        # Publish again
        svc.publish_version("idempotent", 1, "Second")
        second_active = svc.active_version("idempotent")

        # Should still point to v1; changelog updated
        assert first_active["version"] == 1
        assert second_active["version"] == 1
        assert "Second" in second_active["changelog"]

    def test_publish_raises_for_missing_version(self, svc) -> None:
        svc.create_agent(
            agent_id="missing-pub",
            config_json={"id": "missing-pub"},
            author="user",
            changelog="v1",
        )
        with pytest.raises(ValueError, match="not found"):
            svc.publish_version("missing-pub", 99, "publish")

    def test_branch_draft_copies_config_and_files(self, svc) -> None:
        # Create v1, publish, and add a file
        v1 = svc.create_agent(
            agent_id="branch-agent",
            config_json={"id": "branch-agent", "version": 1},
            prompt_content="Original prompt",
            author="user",
            changelog="v1",
        )
        svc.publish_version("branch-agent", 1, "Publish")

        # Add a file to v1
        svc.insert_version_files(
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
        v2 = svc.branch_draft("branch-agent", author="brancher")
        assert v2["version"] == 2
        assert v2["author"] == "brancher"
        assert v2["config_json"] == v1["config_json"]
        assert v2["prompt_content"] == v1["prompt_content"]
        assert "branched from v1" in v2["changelog"]

        # Verify files copied
        v1_files = svc.list_version_files(v1["id"])
        v2_files = svc.list_version_files(v2["id"])
        assert len(v2_files) == len(v1_files)
        assert v2_files[0]["relative_path"] == "prompt.md"
        assert v2_files[0]["content"] == "System prompt"

    def test_branch_draft_raises_without_active_version(self, svc) -> None:
        svc.create_agent(
            agent_id="no-active",
            config_json={"id": "no-active"},
            author="user",
            changelog="v1",
        )
        # v1 is draft, no active version set
        with pytest.raises(ValueError, match="No active version"):
            svc.branch_draft("no-active", author="user")

    def test_branch_draft_does_not_change_active_pointer(self, svc) -> None:
        svc.create_agent(
            agent_id="multi-draft",
            config_json={"id": "multi-draft"},
            author="user",
            changelog="v1",
        )
        svc.publish_version("multi-draft", 1, "Pub")

        active_before = svc.active_version("multi-draft")
        svc.branch_draft("multi-draft", author="user")
        active_after = svc.active_version("multi-draft")

        assert active_before["version"] == active_after["version"]
        assert active_after["version"] == 1

    def test_rollback_creates_new_version_and_activates_it(self, svc) -> None:
        # Create v1, publish
        v1 = svc.create_agent(
            agent_id="rollback-agent",
            config_json={"id": "rollback-agent", "value": 1},
            author="user",
            changelog="v1",
        )
        svc.publish_version("rollback-agent", 1, "Publish v1")

        # Create v2 (different config), publish
        v2_dict = svc.create_version(
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
        )
        svc.activate_version("rollback-agent", v2_dict["id"])

        # Rollback to v1
        v3 = svc.rollback_to(
            "rollback-agent", 1, "Config too risky", author="operator"
        )

        assert v3["version"] == 3
        assert v3["author"] == "operator"
        assert v3["config_json"] == v1["config_json"]
        assert "rollback to v1: Config too risky" in v3["changelog"]

        # Verify active pointer
        active = svc.active_version("rollback-agent")
        assert active["version"] == 3

    def test_rollback_copies_files_from_target(self, svc) -> None:
        v1 = svc.create_agent(
            agent_id="rollback-files",
            config_json={"id": "rollback-files"},
            author="user",
            changelog="v1",
        )
        svc.publish_version("rollback-files", 1, "Pub")

        # Add file to v1
        svc.insert_version_files(
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
        v2 = svc.create_version(
            agent_id="rollback-files",
            source_path="/tmp/test.md",
            source_format="markdown",
            content_snapshot='{"id": "rollback-files"}',
            prompt_snapshot="v2",
            content_hash="xyz",
            author="user",
        )
        svc.activate_version("rollback-files", v2["id"])

        # Rollback to v1
        v3 = svc.rollback_to(
            "rollback-files", 1, "Revert config", author="user"
        )

        # v3 should have v1's files
        v3_files = svc.list_version_files(v3["id"])
        assert len(v3_files) == 1
        assert v3_files[0]["relative_path"] == "config.json"
        assert v3_files[0]["content"] == '{"type": "object"}'

    def test_rollback_rejects_short_reason(self, svc) -> None:
        svc.create_agent(
            agent_id="rollback-reason",
            config_json={"id": "rollback-reason"},
            author="user",
            changelog="v1",
        )
        svc.publish_version("rollback-reason", 1, "Pub")

        with pytest.raises(ValueError, match="at least 3 characters"):
            svc.rollback_to("rollback-reason", 1, "no", author="user")

    def test_rollback_raises_for_missing_target_version(self, svc) -> None:
        svc.create_agent(
            agent_id="rollback-missing",
            config_json={"id": "rollback-missing"},
            author="user",
            changelog="v1",
        )
        svc.publish_version("rollback-missing", 1, "Pub")

        with pytest.raises(ValueError, match="not found"):
            svc.rollback_to("rollback-missing", 99, "Rollback", author="user")
