"""Tests for prompt content sync from inline agent.prompt into prompt_versions."""

from __future__ import annotations

from agentbox.core.service.agents import AgentService


class TestSyncPromptFromDisk:
    def test_creates_v1_when_no_history(self, db) -> None:
        result = AgentService().sync_prompt_from_disk(
            "agent-a", "hello world", author="filesystem"
        )
        assert result is not None
        assert result["version"] == 1
        assert result["is_draft"] == 0
        assert result["author"] == "filesystem"
        assert result["changelog"] == "Imported from disk"
        assert result["content_hash"] is not None

    def test_noop_when_content_unchanged(self, db) -> None:
        AgentService().sync_prompt_from_disk("agent-b", "same content")
        result = AgentService().sync_prompt_from_disk("agent-b", "same content")
        assert result is None
        versions = db.prompt_versions.list_for_agent("agent-b")
        assert len(versions) == 1

    def test_creates_new_version_when_content_changes(self, db) -> None:
        AgentService().sync_prompt_from_disk("agent-c", "v1 content")
        result = AgentService().sync_prompt_from_disk("agent-c", "v2 content")
        assert result is not None
        assert result["version"] == 2
        assert result["changelog"] == "Out-of-band file edit"
        versions = db.prompt_versions.list_for_agent("agent-c")
        assert len(versions) == 2

    def test_respects_explicit_changelog(self, db) -> None:
        result = AgentService().sync_prompt_from_disk(
            "agent-d", "first", changelog="manual sync"
        )
        assert result is not None
        assert result["changelog"] == "manual sync"

    def test_handles_legacy_rows_without_hash(self, db) -> None:
        from agentbox.core.db.agents.prompt import PromptVersion
        prompt_versions = PromptVersion.__table__
        with db.engine.begin() as conn:
            conn.execute(
                prompt_versions.insert().values(
                    agent_id="agent-e",
                    version=1,
                    content="legacy",
                    author="system",
                    changelog="",
                    is_draft=0,
                    content_hash=None,
                    created_at="2025-01-01T00:00:00",
                )
            )
        assert AgentService().sync_prompt_from_disk("agent-e", "legacy") is None
        result = AgentService().sync_prompt_from_disk("agent-e", "updated")
        assert result is not None
        assert result["version"] == 2
