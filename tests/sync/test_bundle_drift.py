"""Tests for watcher bundle-file drift detection.

Covers Phase H: when ``agent.toml`` is unchanged but a referenced bundle
file (system prompt, reference, schema) is edited, the watcher must
still create a new version.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data.manifest import (
    AgentDef,
    AgentSource,
    CompositionConfig,
    RunnerSpec,
)
from agentbox.core.sync.watcher import _bundle_files_drifted
from agentbox.core.versioning.bundle_capture import capture_bundle_files


def _seed_bundle(tmp_path: Path) -> tuple[AgentDef, Path]:
    bundle = tmp_path / "agents" / "demo"
    (bundle / "prompts").mkdir(parents=True)
    (bundle / "agent.toml").write_text(
        '[composition]\nsystem = "prompts/system.md"\n'
    )
    (bundle / "prompts" / "system.md").write_text("v1 system prompt\n")
    agent = AgentDef(
        id="demo",
        source_path=bundle / "agent.toml",
        source_format=AgentSource.STANDALONE_TOML,
        runner=RunnerSpec(),
        composition=CompositionConfig(system="prompts/system.md"),
    )
    return agent, bundle


def test_no_drift_when_files_match(session_store, tmp_path: Path) -> None:
    agent, _ = _seed_bundle(tmp_path)
    files = capture_bundle_files(agent, tmp_path, {})
    session_store.create_version(
        agent_id=agent.id,
        source_path=str(agent.source_path),
        source_format="standalone_toml",
        content_snapshot="{}",
        prompt_snapshot=files[0]["content"],
        content_hash="h",
        files=files,
    )
    assert _bundle_files_drifted(agent, session_store, tmp_path, {}) is False


def test_drift_when_system_prompt_edited(session_store, tmp_path: Path) -> None:
    agent, bundle = _seed_bundle(tmp_path)
    files = capture_bundle_files(agent, tmp_path, {})
    session_store.create_version(
        agent_id=agent.id,
        source_path=str(agent.source_path),
        source_format="standalone_toml",
        content_snapshot="{}",
        prompt_snapshot=files[0]["content"],
        content_hash="h",
        files=files,
    )
    (bundle / "prompts" / "system.md").write_text("v2 — edited content\n")
    assert _bundle_files_drifted(agent, session_store, tmp_path, {}) is True


def test_drift_when_no_versions_yet(session_store, tmp_path: Path) -> None:
    agent, _ = _seed_bundle(tmp_path)
    assert _bundle_files_drifted(agent, session_store, tmp_path, {}) is True


def test_drift_when_legacy_version_has_no_files(
    session_store, tmp_path: Path
) -> None:
    agent, _ = _seed_bundle(tmp_path)
    session_store.create_version(
        agent_id=agent.id,
        source_path=str(agent.source_path),
        source_format="standalone_toml",
        content_snapshot="{}",
        prompt_snapshot="",
        content_hash="legacy",
    )
    assert _bundle_files_drifted(agent, session_store, tmp_path, {}) is True


def test_drift_when_reference_added(session_store, tmp_path: Path) -> None:
    agent, bundle = _seed_bundle(tmp_path)
    files = capture_bundle_files(agent, tmp_path, {})
    session_store.create_version(
        agent_id=agent.id,
        source_path=str(agent.source_path),
        source_format="standalone_toml",
        content_snapshot="{}",
        prompt_snapshot=files[0]["content"],
        content_hash="h",
        files=files,
    )
    (bundle / "ref.md").write_text("new reference\n")
    agent.composition = CompositionConfig(
        system="prompts/system.md",
        references=[{"path": "ref.md"}],
    )
    assert _bundle_files_drifted(agent, session_store, tmp_path, {}) is True


def test_drift_helper_swallows_capture_errors(
    session_store, tmp_path: Path
) -> None:
    """Missing referenced files → capture raises → helper returns False."""
    bundle = tmp_path / "agents" / "broken"
    (bundle / "prompts").mkdir(parents=True)
    (bundle / "prompts" / "system.md").write_text("ok\n")
    agent = AgentDef(
        id="broken",
        source_path=bundle / "agent.toml",
        source_format=AgentSource.STANDALONE_TOML,
        runner=RunnerSpec(),
        composition=CompositionConfig(
            system="prompts/system.md",
            references=[{"path": "missing.md"}],
        ),
    )
    (bundle / "agent.toml").write_text("[composition]\n")
    with pytest.raises(FileNotFoundError):
        capture_bundle_files(agent, tmp_path, {})
    assert _bundle_files_drifted(agent, session_store, tmp_path, {}) is False
