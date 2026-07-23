"""Tests for ``core.service.materialization_io``.

Covers the logic that is NEW in this service (the thin format (de)serialization
is already pinned by ``tests/unit/test_agent_formats.py``):

- export dest-safety guard (empty vs --force)
- export report shape + written/overwritten action
- the import dedup matrix (MIM-01..04): created / unchanged / version_added /
  collision_skipped
- skill import create-then-version

Services self-wire to ``load_settings().db_path`` which the autouse
``AGENTBOX_DATA_DIR`` fixture points at the per-test tmp sqlite, so requesting
the ``db`` fixture seeds the same database the service reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.agents import build_config_json_payload, inline_to_composition
from agentbox.core.data import AgentDef
from agentbox.core.data.errors import AgentNotFound
from agentbox.core.data.payload_types import ExportAction, ImportAction
from agentbox.core.db.database import Database
from agentbox.core.service.agent_formats import AgentFileFormat
from agentbox.core.service.agents import AgentService
from agentbox.core.service.materialization_io import MaterializationService
from agentbox.core.service.workspaces import WorkspaceService


def _make_agent(aid: str, prompt: str) -> None:
    """Seed an agent the way the real import path does — with a composition
    block, so ``get_agent_def().prompt`` round-trips (bare ``prompt_content``
    alone does not surface as ``AgentDef.prompt``)."""
    agent = inline_to_composition(AgentDef(id=aid, description="t", prompt=prompt))
    config_json = {
        **agent.model_dump(mode="json", exclude_none=True),
        **build_config_json_payload(agent),
    }
    AgentService().create_agent(
        agent_id=aid,
        config_json=config_json,
        prompt_content=prompt,
        author="t",
        changelog="init",
    )


def _agent_dir(base: Path, aid: str, prompt: str) -> Path:
    """A claude_code agent folder on disk (frontmatter carries the name)."""
    d = base / f"src_{aid}"
    d.mkdir()
    (d / f"{aid}.md").write_text(
        f"---\nname: {aid}\ndescription: t\n---\n\n{prompt}\n", encoding="utf-8"
    )
    return d


# ── export ──────────────────────────────────────────────────────────────────


def test_export_agent_writes_file_and_report(db: Database, tmp_path: Path) -> None:
    _make_agent("qa", "Do QA work")
    dest = tmp_path / "out"

    report = MaterializationService().export_agent("qa", AgentFileFormat.claude_code, dest)

    assert report["agents"] == ["qa"]
    assert (dest / "qa.md").exists()
    assert report["files"][0]["action"] is ExportAction.written


def test_export_missing_agent_raises(db: Database, tmp_path: Path) -> None:
    with pytest.raises(AgentNotFound):
        MaterializationService().export_agent(
            "ghost", AgentFileFormat.claude_code, tmp_path / "out"
        )


def test_export_refuses_nonempty_dest_without_force(db: Database, tmp_path: Path) -> None:
    _make_agent("qa", "Do QA work")
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "sentinel.txt").write_text("keep me")

    with pytest.raises(ValueError, match="not empty"):
        MaterializationService().export_agent("qa", AgentFileFormat.claude_code, dest)


def test_export_force_overwrites_and_reports_overwritten(
    db: Database, tmp_path: Path
) -> None:
    _make_agent("qa", "Do QA work")
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "qa.md").write_text("stale")

    report = MaterializationService().export_agent(
        "qa", AgentFileFormat.claude_code, dest, force=True
    )

    assert report["files"][0]["action"] is ExportAction.overwritten
    assert "Do QA work" in (dest / "qa.md").read_text()


# ── import dedup matrix ─────────────────────────────────────────────────────


def test_import_creates_new_agent(db: Database, tmp_path: Path) -> None:
    src = _agent_dir(tmp_path, "qa", "Do QA work")

    report = MaterializationService().import_agent(src)

    outcome = report["outcomes"][0]
    assert outcome["action"] is ImportAction.created
    assert outcome["item_id"] == "qa"
    assert AgentService().get_agent_def("qa") is not None


def test_import_same_name_and_prompt_is_unchanged(db: Database, tmp_path: Path) -> None:
    _make_agent("qa", "Do QA work")
    src = _agent_dir(tmp_path, "qa", "Do QA work")

    report = MaterializationService().import_agent(src)

    assert report["outcomes"][0]["action"] is ImportAction.unchanged


def test_import_same_name_new_prompt_adds_version(db: Database, tmp_path: Path) -> None:
    _make_agent("qa", "Old prompt")
    src = _agent_dir(tmp_path, "qa", "A brand new prompt")

    report = MaterializationService().import_agent(src)

    outcome = report["outcomes"][0]
    assert outcome["action"] is ImportAction.version_added
    assert outcome.get("version") == 2
    # regression trap: the version bump must NOT blank prompt_content
    agent = AgentService().get_agent_def("qa")
    assert agent is not None and (agent.prompt or "").strip() == "A brand new prompt"


def test_import_same_prompt_different_name_is_collision(
    db: Database, tmp_path: Path
) -> None:
    _make_agent("qa", "Shared prompt body")
    src = _agent_dir(tmp_path, "clone", "Shared prompt body")

    report = MaterializationService().import_agent(src)

    outcome = report["outcomes"][0]
    assert outcome["action"] is ImportAction.collision_skipped
    assert outcome.get("collision_with") == "qa"
    assert AgentService().get_agent_def("clone") is None  # nothing created


def test_import_no_agent_file_raises(db: Database, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No agent file"):
        MaterializationService().import_agent(empty)


# ── skill import ────────────────────────────────────────────────────────────


def test_import_skill_creates_then_versions(db: Database, tmp_path: Path) -> None:
    skill = tmp_path / "my-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# My Skill\n")

    first = MaterializationService().import_skill(skill)
    assert first["outcomes"][0]["action"] is ImportAction.created
    assert first["outcomes"][0]["item_id"] == "my-skill"

    (skill / "SKILL.md").write_text("# My Skill v2\n")
    second = MaterializationService().import_skill(skill)
    assert second["outcomes"][0]["action"] is ImportAction.version_added


# ── round-trip (both halves agree on normalization) ─────────────────────────


def test_export_then_import_is_unchanged(db: Database, tmp_path: Path) -> None:
    """Export an agent to disk, import it back → must dedup as unchanged.

    This pins that ``dump_agent`` and ``parse_agent`` + ``_checksum`` agree:
    a byte-for-byte re-import of what we just wrote is not a new version.
    """
    _make_agent("qa", "Do QA work")
    mat = MaterializationService()
    dest = tmp_path / "roundtrip"

    mat.export_agent("qa", AgentFileFormat.claude_code, dest)
    report = mat.import_agent(dest)

    assert report["outcomes"][0]["action"] is ImportAction.unchanged


# ── environment export = bulk subagent export ───────────────────────────────


def test_export_environment_writes_every_subagent(
    db: Database, tmp_path: Path
) -> None:
    """A workspace with several subagents exports them all — this is the bulk
    path (there is no separate "export all agents" command)."""
    _make_agent("qa", "Do QA work")
    _make_agent("docs", "Write docs")
    ws = WorkspaceService()
    ws.create_workspace("myenv")
    ws.replace_subagents(
        "myenv",
        [
            {"agent_id": "qa", "alias": "qa"},
            {"agent_id": "docs", "alias": "docs"},
        ],
    )
    dest = tmp_path / "env"

    report = MaterializationService().export_environment("myenv", dest)

    assert set(report["agents"]) == {"qa", "docs"}
    assert (dest / "agents" / "qa.md").exists()
    assert (dest / "agents" / "docs.md").exists()
