"""Regression tests for active-DB-version vs on-disk TOML drift.

Captures the bug where an agent's run used ``timeout_seconds=120`` even
though ``agent.toml`` declared ``timeout_seconds=300`` — caused by a
stale active ``agent_versions`` row left behind after the disk value
changed (the live watcher only creates *draft* versions on file edits).
"""

from __future__ import annotations

import json
from pathlib import Path

from agentbox.core.data.manifest import AgentDef, AgentSource, RunnerSpec
from agentbox.core.deprecated.definitions.loader import DefinitionLoader
from agentbox.core.prompt.versioning.drift import _build_config_json, startup_sweep


def _write_agent(root: Path, agent_id: str, timeout_seconds: int) -> Path:
    agent_dir = root / "agents" / agent_id.replace(".", "_")
    (agent_dir / "prompts").mkdir(parents=True)
    (agent_dir / "prompts" / "system.md").write_text("hi")
    (agent_dir / "agent.toml").write_text(
        f'id = "{agent_id}"\n'
        'description = "test"\n'
        "\n"
        "[runner]\n"
        'kind = "claude_code"\n'
        'model = "haiku"\n'
        f"timeout_seconds = {timeout_seconds}\n"
    )
    return agent_dir / "agent.toml"


def test_config_json_roundtrip_preserves_runner_timeout(tmp_path: Path) -> None:
    """``_build_config_json`` + ``from_db_row`` must preserve runner fields.

    Guards against pydantic defaults silently replacing real values when
    a runner field is round-tripped through the DB snapshot.
    """
    _write_agent(tmp_path, "stage.example", timeout_seconds=300)
    loader = DefinitionLoader(tmp_path)
    agent = loader.get("stage.example")
    assert agent is not None
    assert agent.runner.timeout_seconds == 300

    snapshot = _build_config_json(agent)
    restored = AgentDef.from_db_row({"config_json": snapshot})

    assert restored.runner.timeout_seconds == 300, (
        "round-trip dropped timeout_seconds → got "
        f"{restored.runner.timeout_seconds}; this is how the 120s default "
        "leaks back in when the snapshot omits the field"
    )
    assert restored.runner.kind == agent.runner.kind
    assert restored.runner.model == agent.runner.model


def test_active_version_diverged_from_disk_is_detectable(
    session_store, tmp_path: Path
) -> None:
    """When the active DB version's runner config differs from the disk TOML,
    the difference is visible — operators (and tests) can detect the drift
    instead of silently running with the stale value.
    """
    _write_agent(tmp_path, "stage.example", timeout_seconds=300)
    loader = DefinitionLoader(tmp_path)
    disk_agent = loader.get("stage.example")
    assert disk_agent is not None and disk_agent.runner.timeout_seconds == 300

    stale_snapshot = json.dumps(
        {
            "id": "stage.example",
            "runner": {"kind": "claude_code", "model": "haiku", "timeout_seconds": 120},
        }
    )
    v = session_store.create_version(
        agent_id="stage.example",
        source_path=str(loader.legacy_agents_path / "stage_example" / "agent.toml"),
        source_format="bundle",
        content_snapshot=stale_snapshot,
        prompt_snapshot="",
        content_hash="stale",
        author="filesystem",
        config_json=stale_snapshot,
        prompt_content="hi",
        source="manifest",
    )
    session_store.activate_version("stage.example", v["id"])

    active = session_store.get_active_version("stage.example")
    assert active is not None
    active_agent = AgentDef.from_db_row(active)

    assert active_agent.runner.timeout_seconds == 120
    assert disk_agent.runner.timeout_seconds == 300
    assert active_agent.runner.timeout_seconds != disk_agent.runner.timeout_seconds, (
        "this asymmetry is exactly what caused run 4d1260b4 to time out at "
        "120s while agent.toml said 300s — the runtime resolver picks the "
        "active DB version, not the disk file"
    )


def test_startup_sweep_heals_orphaned_versions(session_store, tmp_path: Path) -> None:
    """If versions exist but no active pointer, sweep must promote one.

    Reproduces the 'no active version' state the user observed in the UI:
    versions in the table but ``active_agent_versions`` empty, leaving
    ``_resolve_agent`` to silently fall back to the disk loader (and giving
    the operator no version to inspect in the UI).
    """
    agent_toml = _write_agent(tmp_path, "stage.example", timeout_seconds=300)
    agent = AgentDef(
        id="stage.example",
        source_path=agent_toml,
        source_format=AgentSource.BUNDLE,
        runner=RunnerSpec(timeout_seconds=300),
    )
    seed = json.dumps({"id": "stage.example", "runner": {"timeout_seconds": 120}})
    session_store.create_version(
        agent_id="stage.example",
        source_path=str(agent_toml),
        source_format="bundle",
        content_snapshot=seed,
        prompt_snapshot="",
        content_hash="orphan",
        author="filesystem",
        config_json=seed,
        prompt_content="",
        source="manifest",
    )
    assert session_store.get_active_version("stage.example") is None

    startup_sweep([agent], session_store, project_root=tmp_path)

    active = session_store.get_active_version("stage.example")
    assert active is not None, (
        "sweep must heal the missing active pointer so the UI shows a "
        "current version and _resolve_agent stops falling back silently"
    )


def test_startup_sweep_prefers_committed_over_draft_when_healing(
    session_store, tmp_path: Path
) -> None:
    """Heal step picks the latest *committed* version, not a stray draft.

    Uses a SAME-status agent (matching file hash) so the heal step is the
    only thing that touches the active pointer.
    """
    agent_toml = _write_agent(tmp_path, "stage.example", timeout_seconds=300)
    import hashlib

    file_hash = hashlib.sha256(agent_toml.read_bytes()).hexdigest()
    agent = AgentDef(
        id="stage.example",
        source_path=agent_toml,
        source_format=AgentSource.BUNDLE,
        runner=RunnerSpec(timeout_seconds=300),
    )
    snap = json.dumps({"id": "stage.example"})
    committed = session_store.create_version(
        agent_id="stage.example",
        source_path=str(agent_toml),
        source_format="bundle",
        content_snapshot=snap,
        prompt_snapshot="",
        content_hash=file_hash,  # matches disk → status SAME
        author="filesystem",
        config_json=snap,
        source="manifest",
        is_draft=False,
    )
    session_store.create_version(
        agent_id="stage.example",
        source_path=str(agent_toml),
        source_format="bundle",
        content_snapshot=snap,
        prompt_snapshot="",
        content_hash=file_hash,
        author="filesystem",
        config_json=snap,
        source="manifest",
        is_draft=True,
    )

    startup_sweep([agent], session_store, project_root=tmp_path)

    active = session_store.get_active_version("stage.example")
    assert active is not None
    assert active["id"] == committed["id"], (
        "drafts are unreviewed — heal must pick the latest committed version"
    )
