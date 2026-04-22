"""Tests for prompt read/write helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentbox.core import prompts
from agentbox.core.definitions import AgentDef, RunnerSpec


def _agent(prompt_path: str | None = "prompts/main.md") -> AgentDef:
    return AgentDef(
        id="t",
        prompt_path=prompt_path,
        runner=RunnerSpec(kind="subprocess", command=["true"]),
    )


def test_read_missing_returns_empty(tmp_path: Path) -> None:
    doc = prompts.read(_agent(), tmp_path)
    assert doc.content == ""
    assert doc.size == 0
    assert doc.mtime == ""


def test_round_trip(tmp_path: Path) -> None:
    written = prompts.write(_agent(), tmp_path, "Hello\n")
    assert written.content == "Hello\n"
    assert written.size == 6
    assert (tmp_path / "prompts/main.md").read_text() == "Hello\n"
    re_read = prompts.read(_agent(), tmp_path)
    assert re_read.content == "Hello\n"


def test_no_prompt_path_errors(tmp_path: Path) -> None:
    with pytest.raises(prompts.PromptError) as exc:
        prompts.read(_agent(prompt_path=None), tmp_path)
    assert exc.value.code == "no_prompt"


def test_path_traversal_blocked(tmp_path: Path) -> None:
    with pytest.raises(prompts.PromptError) as exc:
        prompts.read(_agent("../escape.md"), tmp_path)
    assert exc.value.code == "path_escape"
