"""Tests for materialize_subagents and combined workspace materialize.

Covers RESOURCES_PLAN Phase 2 / task F5: ensures subagents render into
each backend's agents/ folder and that file paths match the contract.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.workspaces.generation.materialize import (
    BACKEND_AGENT_DIRS,
    materialize_subagents,
)


def test_materialize_subagents_writes_to_all_backend_dirs(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    resolved = [
        {
            "workspace_id": "w1",
            "agent_id": "a1",
            "alias": "researcher",
            "description": "Searches the web for facts",
            "prompt_content": "You are a research subagent.",
        }
    ]
    outcomes = materialize_subagents(workdir, resolved)
    assert len(outcomes) == 1
    assert len(outcomes[0].files_written) == len(BACKEND_AGENT_DIRS)
    for rel in BACKEND_AGENT_DIRS:
        f = workdir / rel / "researcher.md"
        assert f.exists()
        body = f.read_text()
        assert body.startswith("---\n")
        assert "name: researcher" in body
        assert "description: Searches the web for facts" in body
        assert "You are a research subagent." in body


def test_multiple_subagents_distinct_files(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    resolved = [
        {
            "workspace_id": "w1",
            "agent_id": "a1",
            "alias": "alpha",
            "description": None,
            "prompt_content": "alpha body",
        },
        {
            "workspace_id": "w1",
            "agent_id": "a2",
            "alias": "beta",
            "description": "beta desc",
            "prompt_content": "beta body",
        },
    ]
    materialize_subagents(workdir, resolved)
    for rel in BACKEND_AGENT_DIRS:
        files = sorted(p.name for p in (workdir / rel).iterdir())
        assert files == ["alpha.md", "beta.md"]


def test_no_description_omits_description_line(tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    materialize_subagents(
        workdir,
        [
            {
                "workspace_id": "w",
                "agent_id": "a",
                "alias": "x",
                "description": None,
                "prompt_content": "body",
            }
        ],
    )
    body = (workdir / ".claude/agents/x.md").read_text()
    assert "description:" not in body
