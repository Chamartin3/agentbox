"""Tests for ManifestWriter: round-trip, comment preservation, validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.deprecated.definitions import ManifestWriter, PatchError

SAMPLE = """\
project = "demo"

# Top-level orchestrator.
[[agents]]
id = "main"
description = "main agent"
prompt_path = "prompts/main.md"
workspace = "ws/main"

  [agents.runner]
  kind = "claude_code"
  model = "haiku"
  allowed_tools = ["Task"]
  timeout_seconds = 600

[[agents]]
id = "secondary"
description = "secondary agent"

  [agents.runner]
  kind = "subprocess"
  command = ["echo", "hi"]
"""


def _setup(tmp_path: Path) -> ManifestWriter:
    (tmp_path / "agentbox.toml").write_text(SAMPLE)
    return ManifestWriter(tmp_path)


def test_read_parsed(tmp_path: Path) -> None:
    m = _setup(tmp_path).read_parsed()
    assert m.project == "demo"
    assert [a.id for a in m.agents] == ["main", "secondary"]
    assert m.agents[0].runner.model == "haiku"


def test_patch_agent_top_level(tmp_path: Path) -> None:
    w = _setup(tmp_path)
    updated = w.patch_agent("main", {"description": "renamed"})
    assert updated.description == "renamed"
    text = w.read_text()
    assert "Top-level orchestrator." in text  # comment preserved
    assert 'description = "renamed"' in text


def test_patch_runner_fields(tmp_path: Path) -> None:
    w = _setup(tmp_path)
    updated = w.patch_agent(
        "main",
        {"runner": {"model": "sonnet", "allowed_tools": ["Task", "AskUserQuestion"]}},
    )
    assert updated.runner.model == "sonnet"
    assert updated.runner.allowed_tools == ["Task", "AskUserQuestion"]
    text = w.read_text()
    assert "Top-level orchestrator." in text


def test_patch_unknown_agent(tmp_path: Path) -> None:
    w = _setup(tmp_path)
    with pytest.raises(PatchError) as exc:
        w.patch_agent("ghost", {"description": "x"})
    assert exc.value.code == "unknown_agent"


def test_patch_forbidden_field(tmp_path: Path) -> None:
    w = _setup(tmp_path)
    with pytest.raises(PatchError) as exc:
        w.patch_agent("main", {"id": "renamed"})
    assert exc.value.code == "forbidden_field"


def test_patch_validation_failure(tmp_path: Path) -> None:
    w = _setup(tmp_path)
    # session_mode must be "headless" | "persistent"
    with pytest.raises(PatchError) as exc:
        w.patch_agent("main", {"session_mode": "nonsense"})
    assert exc.value.code == "validation_failed"
    # File untouched after rejected patch.
    assert (
        "session_mode" not in w.read_text()
        or 'session_mode = "headless"' not in w.read_text()
    )


def test_patch_removes_field_when_null(tmp_path: Path) -> None:
    w = _setup(tmp_path)
    w.patch_agent("main", {"workspace": None})
    assert "workspace = " not in w.read_text()
