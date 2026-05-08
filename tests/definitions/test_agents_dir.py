"""Tests for agents.d/ directory scanner."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data.manifest import AgentSource
from agentbox.core.definitions.agents_dir import scan_agents_dir


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_empty_dir_returns_empty(tmp_path: Path) -> None:
    agents = scan_agents_dir(tmp_path / "agents.d")
    assert agents == []


def test_ignores_dotfiles(tmp_path: Path) -> None:
    d = tmp_path / "agents.d"
    _write(d / ".hidden.toml", 'id = "hidden"\n')
    _write(d / ".hidden.md", "---\nid: hidden-md\n---\nbody\n")
    agents = scan_agents_dir(d)
    assert agents == []


def test_ignores_readme(tmp_path: Path) -> None:
    d = tmp_path / "agents.d"
    _write(d / "README.md", "Just docs")
    agents = scan_agents_dir(d)
    assert agents == []


def test_loads_toml_agent(tmp_path: Path) -> None:
    d = tmp_path / "agents.d"
    _write(
        d / "writer.toml",
        """\
id = "writer"
description = "Writes drafts"
workspace = "default"

[runner]
kind = "token"
timeout_seconds = 120
""",
    )
    agents = scan_agents_dir(d)
    assert len(agents) == 1
    assert agents[0].id == "writer"
    assert agents[0].description == "Writes drafts"
    assert agents[0].source_format == AgentSource.STANDALONE_TOML


def test_loads_markdown_agent(tmp_path: Path) -> None:
    d = tmp_path / "agents.d"
    _write(
        d / "researcher.md",
        """\
---
id: researcher
description: Researches topics
---
Research body
""",
    )
    agents = scan_agents_dir(d)
    assert len(agents) == 1
    assert agents[0].id == "researcher"
    assert agents[0].source_format == AgentSource.MARKDOWN


def test_loads_legacy_dir_agent(tmp_path: Path) -> None:
    d = tmp_path / "agents.d"
    _write(
        d / "legacy-agent" / "agent.toml",
        """\
id = "legacy-agent"
description = "From legacy dir"
""",
    )
    _write(d / "legacy-agent" / "prompts" / "system.md", "Legacy prompt")
    agents = scan_agents_dir(d)
    assert len(agents) >= 1
    legacy = [a for a in agents if a.id == "legacy-agent"]
    assert len(legacy) == 1
    assert legacy[0].source_format == AgentSource.LEGACY_DIR


def test_sorted_order(tmp_path: Path) -> None:
    d = tmp_path / "agents.d"
    _write(d / "b_agent.md", "---\nid: b-agent\n---\nbody b\n")
    _write(d / "a_agent.md", "---\nid: a-agent\n---\nbody a\n")
    agents = scan_agents_dir(d)
    assert agents[0].id == "a-agent"
    assert agents[1].id == "b-agent"


def test_skips_invalid_file_gracefully(tmp_path: Path) -> None:
    d = tmp_path / "agents.d"
    _write(d / "bad.md", "no frontmatter here")
    agents = scan_agents_dir(d)  # Should not raise
    assert len(agents) == 0
