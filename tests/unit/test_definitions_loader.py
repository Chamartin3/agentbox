"""DefinitionLoader: directory discovery, inline+directory merge, defaults."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.constants import RunnerKind
from agentbox.core.definitions import DefinitionLoader


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_missing_manifest_returns_empty(tmp_path: Path) -> None:
    """No agentbox.toml → empty manifest with sensible defaults."""
    m = DefinitionLoader(tmp_path).load()
    assert m.project == "default"
    assert m.agents == []
    assert m.workspaces == []


def test_markdown_only_agent_auto_discovered(tmp_path: Path) -> None:
    """An agent dir with only prompts/system.md becomes a default token agent."""
    _write(tmp_path / "agents" / "writer" / "prompts" / "system.md", "be helpful")
    m = DefinitionLoader(tmp_path).load()
    assert [a.id for a in m.agents] == ["writer"]
    agent = m.agents[0]
    assert agent.runner.kind == RunnerKind.TOKEN
    assert agent.workspace == "default"
    assert agent.prompt_path is not None and agent.prompt_path.endswith("system.md")


def test_agent_toml_overrides_defaults(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents" / "claudette" / "agent.toml",
        """
id = "claudette"
description = "uses claude"
workspace = "research"

[runner]
kind = "claude_code"
model = "haiku"
allowed_tools = ["Read", "Grep"]
""",
    )
    m = DefinitionLoader(tmp_path).load()
    a = m.agents[0]
    assert a.id == "claudette"
    assert a.workspace == "research"
    assert a.runner.kind == RunnerKind.CLAUDE_CODE
    assert a.runner.model == "haiku"
    assert a.runner.allowed_tools == ["Read", "Grep"]


def test_inline_agent_wins_over_directory_on_id_clash(tmp_path: Path) -> None:
    """Inline agentbox.toml entries override directory-discovered ones."""
    _write(
        tmp_path / "agents" / "dup" / "agent.toml",
        """
id = "dup"
description = "from dir"

[runner]
kind = "token"
""",
    )
    _write(
        tmp_path / "agentbox.toml",
        """
project = "merge-test"

[[agents]]
id = "dup"
description = "from inline"

  [agents.runner]
  kind = "claude_code"
""",
    )
    m = DefinitionLoader(tmp_path).load()
    assert m.project == "merge-test"
    assert len(m.agents) == 1
    assert m.agents[0].description == "from inline"
    assert m.agents[0].runner.kind == RunnerKind.CLAUDE_CODE


def test_get_returns_none_for_unknown_agent(tmp_path: Path) -> None:
    loader = DefinitionLoader(tmp_path)
    assert loader.get("missing") is None


def test_list_workspaces_reads_inline(tmp_path: Path) -> None:
    _write(
        tmp_path / "agentbox.toml",
        """
[[workspaces]]
name = "default"
path = "workdir/default"
description = "primary"
""",
    )
    workspaces = DefinitionLoader(tmp_path).list_workspaces()
    assert [w.name for w in workspaces] == ["default"]
    assert workspaces[0].path == "workdir/default"
