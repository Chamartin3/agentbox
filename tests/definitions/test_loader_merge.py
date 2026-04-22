"""Tests for loader merge order — inline + standalone + markdown agents
collision precedence, source_path and source_format."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data.manifest import AgentSource
from agentbox.core.definitions import DefinitionLoader


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_inline_agents_loaded(tmp_path: Path) -> None:
    _write(
        tmp_path / "agentbox.toml",
        """\
[[agents]]
id = "inline-agent"
description = "From inline"
""",
    )
    m = DefinitionLoader(tmp_path).load()
    assert len(m.agents) == 1
    assert m.agents[0].id == "inline-agent"
    assert m.agents[0].description == "From inline"


def test_agents_d_toml_loaded(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents.d" / "toml-agent.toml",
        """\
id = "toml-agent"
description = "From standalone toml"
""",
    )
    m = DefinitionLoader(tmp_path).load()
    assert len(m.agents) == 1
    assert m.agents[0].id == "toml-agent"


def test_agents_d_md_loaded(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents.d" / "md-agent.md",
        """\
---
id: md-agent
description: From markdown
---
Body
""",
    )
    m = DefinitionLoader(tmp_path).load()
    assert len(m.agents) == 1
    assert m.agents[0].id == "md-agent"


def test_legacy_agents_dir_loaded(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents" / "legacy" / "agent.toml",
        """\
id = "legacy"
description = "From legacy dir"
""",
    )
    _write(tmp_path / "agents" / "legacy" / "prompts" / "system.md", "Body")
    m = DefinitionLoader(tmp_path).load()
    ids = {a.id for a in m.agents}
    assert "legacy" in ids


def test_source_format_set_on_all(tmp_path: Path) -> None:
    _write(
        tmp_path / "agentbox.toml",
        """\
[[agents]]
id = "inline"
description = "inline"
""",
    )
    _write(
        tmp_path / "agents.d" / "standalone.toml",
        'id = "standalone"\ndescription = "standalone"\n',
    )
    _write(
        tmp_path / "agents.d" / "markdown.md",
        """\
---
id: markdown
description: markdown
---
Body
""",
    )
    _write(
        tmp_path / "agents" / "legacy" / "agent.toml",
        'id = "legacy"\ndescription = "legacy"\n',
    )
    _write(tmp_path / "agents" / "legacy" / "prompts" / "system.md", "Body")

    m = DefinitionLoader(tmp_path).load()
    by_id = {a.id: a for a in m.agents}
    assert by_id["inline"].source_format == AgentSource.INLINE_TOML
    assert by_id["standalone"].source_format == AgentSource.STANDALONE_TOML
    assert by_id["markdown"].source_format == AgentSource.MARKDOWN
    assert by_id["legacy"].source_format == AgentSource.LEGACY_DIR


def test_inline_overrides_markdown(tmp_path: Path) -> None:
    _write(
        tmp_path / "agentbox.toml",
        """\
[[agents]]
id = "dup"
description = "from inline (should win)"
""",
    )
    _write(
        tmp_path / "agents.d" / "dup.md",
        """\
---
id: dup
description: from markdown
---
Body
""",
    )
    m = DefinitionLoader(tmp_path).load()
    assert m.agents[0].description == "from inline (should win)"


def test_source_path_set(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents.d" / "path-check.md",
        """\
---
id: path-check
---
Body
""",
    )
    m = DefinitionLoader(tmp_path).load()
    a = m.agents[0]
    assert a.source_path is not None
    assert a.source_path.name == "path-check.md"
