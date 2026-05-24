"""Tests for the drift detector — NEW / SAME / DRIFTED / UNKNOWN_SOURCE."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data import AgentDef, AgentSource, RunnerSpec
from agentbox.core.prompt.versioning.drift import (
    AgentDriftStatus,
    check_drift,
    startup_sweep,
)


def _agent(
    agent_id: str = "drift-test",
    source_path: Path | None = None,
) -> AgentDef:
    return AgentDef(
        id=agent_id,
        source_path=source_path,
        source_format=AgentSource.STANDALONE_TOML,
        runner=RunnerSpec(),
    )


class TestCheckDrift:
    def test_new_when_no_versions(self, session_store) -> None:
        agent = _agent(source_path=Path("/tmp/nonexistent.toml"))
        status = check_drift(agent, session_store)
        assert status == AgentDriftStatus.NEW

    def test_new_when_latest_exists_but_file_missing(self, session_store) -> None:
        agent = _agent(source_path=Path("/tmp/nonexistent.toml"))
        # Seed a version so latest_version returns something
        session_store.create_version(
            agent_id="drift-test",
            source_path="/tmp/nonexistent.toml",
            source_format="standalone_toml",
            content_snapshot="{}",
            prompt_snapshot="",
            content_hash="oldhash",
            author="system",
        )
        status = check_drift(agent, session_store)
        assert status == AgentDriftStatus.UNKNOWN_SOURCE

    def test_same_when_file_hash_matches(self, session_store, tmp_path) -> None:
        f = tmp_path / "agent.toml"
        f.write_text("id = 'test'")
        agent = _agent(source_path=f)
        import hashlib

        h = hashlib.sha256(f.read_bytes()).hexdigest()
        session_store.create_version(
            agent_id="drift-test",
            source_path=str(f),
            source_format="standalone_toml",
            content_snapshot="{}",
            prompt_snapshot="",
            content_hash=h,
            author="system",
        )
        assert check_drift(agent, session_store) == AgentDriftStatus.SAME

    def test_drifted_when_hash_differs(self, session_store, tmp_path) -> None:
        f = tmp_path / "agent.toml"
        f.write_text("original content")
        agent = _agent(source_path=f)
        session_store.create_version(
            agent_id="drift-test",
            source_path=str(f),
            source_format="standalone_toml",
            content_snapshot="{}",
            prompt_snapshot="",
            content_hash="differenthash",
            author="system",
        )
        assert check_drift(agent, session_store) == AgentDriftStatus.DRIFTED

    def test_unknown_source_when_no_source_path(self, session_store) -> None:
        agent = _agent(source_path=None)
        assert check_drift(agent, session_store) == AgentDriftStatus.UNKNOWN_SOURCE


class TestStartupSweep:
    def test_creates_v1_for_new_agent(self, session_store, tmp_path) -> None:
        f = tmp_path / "agent.toml"
        f.write_text("id = 'test'")
        agent = _agent(agent_id="sweep-new", source_path=f)
        startup_sweep([agent], session_store)
        latest = session_store.latest_version("sweep-new")
        assert latest is not None
        assert latest["version"] == 1
        assert latest["author"] == "filesystem"
        assert "initial" in latest["changelog"]

    def test_creates_version_for_drifted_agent(self, session_store, tmp_path) -> None:
        f = tmp_path / "agent.toml"
        f.write_text("original")
        agent = _agent(agent_id="sweep-drift", source_path=f)
        # Seed mismatched version
        session_store.create_version(
            agent_id="sweep-drift",
            source_path=str(f),
            source_format="standalone_toml",
            content_snapshot="{}",
            prompt_snapshot="",
            content_hash="oldhash",
            author="system",
        )
        f.write_text("modified content")
        startup_sweep([agent], session_store)
        latest = session_store.latest_version("sweep-drift")
        assert latest is not None
        assert latest["version"] == 2
        assert latest["author"] == "filesystem"
        assert "out-of-band" in latest["changelog"]

    def test_noop_for_same_agent(self, session_store, tmp_path) -> None:
        f = tmp_path / "agent.toml"
        f.write_text("id = 'test'")
        agent = _agent(agent_id="sweep-same", source_path=f)
        import hashlib

        h = hashlib.sha256(f.read_bytes()).hexdigest()
        session_store.create_version(
            agent_id="sweep-same",
            source_path=str(f),
            source_format="standalone_toml",
            content_snapshot="{}",
            prompt_snapshot="",
            content_hash=h,
            author="system",
        )
        startup_sweep([agent], session_store)
        versions = session_store.list_versions("sweep-same")
        assert len(versions) == 1

    def test_skips_unknown_source(self, session_store) -> None:
        agent = _agent(agent_id="skip-me", source_path=None)
        startup_sweep([agent], session_store)
        assert session_store.latest_version("skip-me") is None

    def test_handles_mixed_agents(self, session_store, tmp_path) -> None:
        new_f = tmp_path / "new.toml"
        new_f.write_text("new agent")
        new_agent = _agent(agent_id="mixed-new", source_path=new_f)

        same_f = tmp_path / "same.toml"
        same_f.write_text("same agent")
        same_agent = _agent(agent_id="mixed-same", source_path=same_f)
        import hashlib

        h = hashlib.sha256(same_f.read_bytes()).hexdigest()
        session_store.create_version(
            agent_id="mixed-same",
            source_path=str(same_f),
            source_format="standalone_toml",
            content_snapshot="{}",
            prompt_snapshot="",
            content_hash=h,
            author="system",
        )

        startup_sweep([new_agent, same_agent], session_store)
        assert session_store.latest_version("mixed-new") is not None
        assert session_store.latest_version("mixed-new")["version"] == 1
        versions_same = session_store.list_versions("mixed-same")
        assert len(versions_same) == 1
