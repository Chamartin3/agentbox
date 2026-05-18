"""Tests for prompt content sync from disk into prompt_versions."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data.manifest import AgentDef, AgentSource, RunnerSpec
from agentbox.core.prompt.versioning.drift import startup_sweep


def _agent_with_prompt(
    agent_id: str, source_path: Path, prompt_path: str
) -> AgentDef:
    return AgentDef(
        id=agent_id,
        source_path=source_path,
        source_format=AgentSource.STANDALONE_TOML,
        prompt_path=prompt_path,
        runner=RunnerSpec(),
    )


class TestSyncPromptFromDisk:
    def test_creates_v1_when_no_history(self, session_store) -> None:
        result = session_store.sync_prompt_from_disk(
            "agent-a", "hello world", author="filesystem"
        )
        assert result is not None
        assert result["version"] == 1
        assert result["is_draft"] == 0
        assert result["author"] == "filesystem"
        assert result["changelog"] == "Imported from disk"
        assert result["content_hash"] is not None

    def test_noop_when_content_unchanged(self, session_store) -> None:
        session_store.sync_prompt_from_disk("agent-b", "same content")
        result = session_store.sync_prompt_from_disk("agent-b", "same content")
        assert result is None
        versions = session_store.list_prompt_versions("agent-b")
        assert len(versions) == 1

    def test_creates_new_version_when_content_changes(self, session_store) -> None:
        session_store.sync_prompt_from_disk("agent-c", "v1 content")
        result = session_store.sync_prompt_from_disk("agent-c", "v2 content")
        assert result is not None
        assert result["version"] == 2
        assert result["changelog"] == "Out-of-band file edit"
        versions = session_store.list_prompt_versions("agent-c")
        assert len(versions) == 2

    def test_respects_explicit_changelog(self, session_store) -> None:
        result = session_store.sync_prompt_from_disk(
            "agent-d", "first", changelog="manual sync"
        )
        assert result is not None
        assert result["changelog"] == "manual sync"

    def test_handles_legacy_rows_without_hash(self, session_store) -> None:
        # Simulate a legacy row written before content_hash existed.
        from agentbox.core.data.schema import prompt_versions

        with session_store.engine.begin() as conn:
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
        # Same content => still a no-op (hash computed from content).
        assert session_store.sync_prompt_from_disk("agent-e", "legacy") is None
        # Different content => new version.
        result = session_store.sync_prompt_from_disk("agent-e", "updated")
        assert result is not None
        assert result["version"] == 2


class TestStartupSweepPromptSync:
    def test_sweep_captures_prompt_on_first_load(
        self, session_store, tmp_path
    ) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        toml_path = agents_dir / "a.toml"
        toml_path.write_text("id = 'a'")
        prompt_file = agents_dir / "a.md"
        prompt_file.write_text("hello prompt")

        agent = _agent_with_prompt("a", toml_path, str(prompt_file))
        startup_sweep([agent], session_store, project_root=tmp_path)

        versions = session_store.list_prompt_versions("a")
        assert len(versions) == 1
        assert versions[0]["content"] == "hello prompt"
        assert versions[0]["author"] == "filesystem"

    def test_sweep_captures_out_of_band_prompt_edit(
        self, session_store, tmp_path
    ) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        toml_path = agents_dir / "b.toml"
        toml_path.write_text("id = 'b'")
        prompt_file = agents_dir / "b.md"
        prompt_file.write_text("original")

        agent = _agent_with_prompt("b", toml_path, str(prompt_file))
        startup_sweep([agent], session_store, project_root=tmp_path)

        # Edit prompt only — agent.toml unchanged
        prompt_file.write_text("edited on disk")
        startup_sweep([agent], session_store, project_root=tmp_path)

        versions = session_store.list_prompt_versions("b")
        assert len(versions) == 2
        # list returns desc by version
        assert versions[0]["version"] == 2
        assert versions[0]["content"] == "edited on disk"
        assert versions[0]["changelog"] == "Out-of-band file edit"

    def test_sweep_is_idempotent_when_prompt_unchanged(
        self, session_store, tmp_path
    ) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        toml_path = agents_dir / "c.toml"
        toml_path.write_text("id = 'c'")
        prompt_file = agents_dir / "c.md"
        prompt_file.write_text("stable")

        agent = _agent_with_prompt("c", toml_path, str(prompt_file))
        startup_sweep([agent], session_store, project_root=tmp_path)
        startup_sweep([agent], session_store, project_root=tmp_path)
        startup_sweep([agent], session_store, project_root=tmp_path)

        versions = session_store.list_prompt_versions("c")
        assert len(versions) == 1

    def test_sweep_skips_agents_without_prompt(
        self, session_store, tmp_path
    ) -> None:
        toml_path = tmp_path / "d.toml"
        toml_path.write_text("id = 'd'")
        agent = AgentDef(
            id="d",
            source_path=toml_path,
            source_format=AgentSource.STANDALONE_TOML,
            runner=RunnerSpec(),
        )
        startup_sweep([agent], session_store, project_root=tmp_path)
        assert session_store.list_prompt_versions("d") == []
