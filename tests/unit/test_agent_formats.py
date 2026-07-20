"""Round-trip checks for agent file (de)serialization."""
from __future__ import annotations

import pytest

from agentbox.core.data import AgentDef
from agentbox.core.service.agent_formats import FORMATS, dump_agent, parse_agent


@pytest.fixture
def agent() -> AgentDef:
    return AgentDef(
        id="greeter",
        description="Greets people",
        prompt="You are a friendly greeter.\nSay hi.",
        tools=["fs.read", "shell.exec"],
    )


@pytest.mark.parametrize("fmt", FORMATS)
def test_dump_names_the_file_after_the_agent(agent: AgentDef, fmt: str) -> None:
    files = dump_agent(agent, fmt)
    assert files, "expected at least one file"
    assert files[0][0].startswith("greeter.")


def test_claude_code_round_trip(agent: AgentDef) -> None:
    _, content = dump_agent(agent, "claude_code")[0]
    back = parse_agent(content, "claude_code")
    # Claude Code subagent md carries name/description/prompt (no tool list).
    assert (back.id, back.description) == ("greeter", "Greets people")
    assert back.prompt == agent.prompt


def test_opencode_round_trip_keeps_tools(agent: AgentDef) -> None:
    _, content = dump_agent(agent, "opencode")[0]
    back = parse_agent(content, "opencode", agent_id="greeter")
    assert back.id == "greeter"
    assert back.tools == ["fs.read", "shell.exec"]
    assert back.prompt == agent.prompt


def test_opencode_needs_id_hint(agent: AgentDef) -> None:
    _, content = dump_agent(agent, "opencode")[0]
    with pytest.raises(ValueError):
        parse_agent(content, "opencode")


def test_codex_round_trip_uses_subagent_toml(agent: AgentDef) -> None:
    files = dump_agent(agent, "codex")
    assert [n for n, _ in files] == ["greeter.toml"]
    _, content = files[0]
    # Real Codex subagent shape (name / description / developer_instructions).
    assert "developer_instructions" in content
    back = parse_agent(content, "codex")
    assert (back.id, back.description) == ("greeter", "Greets people")
    assert back.prompt == agent.prompt  # prompt survives round-trip


def test_unknown_format_raises(agent: AgentDef) -> None:
    with pytest.raises(ValueError):
        dump_agent(agent, "nope")
