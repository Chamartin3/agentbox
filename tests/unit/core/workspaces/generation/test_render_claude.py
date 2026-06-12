"""Tests for the generator render function — Claude recipe."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agentbox.core.workspaces.generation.config import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkenvConfig,
)
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.workspaces.generation.recipe import load_recipe


def _make_fixture_config(**overrides: object) -> WorkenvConfig:
    kwargs: dict = {
        "name": "test-workspace",
        "description": "A test workspace",
        "env_doc": "# Hello\nThis is the env doc.",
        "agents": [
            AgentRef(id="main-agent", role="main"),
            AgentRef(id="sub-1", role="subagent"),
            AgentRef(id="sub-2", role="subagent"),
        ],
        "resources": [ResourceRef(id="res-1")],
        "skills": [ResourceRef(id="skill-1"), ResourceRef(id="skill-2")],
        "mcp_servers": [
            McpRef(
                name="my-mcp",
                config={"url": "http://localhost:8080"},
            ),
        ],
        "permissions": Permissions(
            data={"allow": ["Read", "Write"], "deny": ["Bash"]}
        ),
        "env": {"KEY": "VAL"},
    }
    kwargs.update(overrides)
    return WorkenvConfig(**kwargs)


class TestRenderClaude:
    def test_render_minimal(self) -> None:
        config = WorkenvConfig(name="minimal")
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            result = render(Path(td), config, recipe)
            assert result.target_dir == Path(td)
            assert len(result.written_paths) >= 1

            claude_md = Path(td) / "CLAUDE.md"
            assert claude_md.exists()

    def test_render_full(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe)

            claude_md = Path(td) / "CLAUDE.md"
            assert claude_md.exists()
            content = claude_md.read_text()
            assert "test-workspace" in content
            assert "env doc" in content

    def test_render_subagents(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe)

            sub1 = Path(td) / ".claude" / "agents" / "sub-1.md"
            sub2 = Path(td) / ".claude" / "agents" / "sub-2.md"
            assert sub1.exists()
            assert sub2.exists()
            assert "sub-1" in sub1.read_text()

    def test_render_main_agent_not_a_subagent(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe)

            main_agent_file = Path(td) / ".claude" / "agents" / "main-agent.md"
            assert not main_agent_file.exists()

    def test_render_mcp_config(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe)

            mcp_file = Path(td) / ".mcp.json"
            assert mcp_file.exists()
            mcp_data = json.loads(mcp_file.read_text())
            assert "mcpServers" in mcp_data
            assert "my-mcp" in mcp_data["mcpServers"]
            assert (
                mcp_data["mcpServers"]["my-mcp"]["url"]
                == "http://localhost:8080"
            )

    def test_render_permissions(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe)

            perm_file = Path(td) / ".claude" / "settings.json"
            assert perm_file.exists()
            perm_data = json.loads(perm_file.read_text())
            assert "permissions" in perm_data
            assert perm_data["permissions"]["allow"] == ["Read", "Write"]

    def test_idempotent(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            result1 = render(Path(td), config, recipe)
            result2 = render(Path(td), config, recipe)
            assert len(result1.written_paths) == len(result2.written_paths)

    def test_no_mcp_when_empty(self) -> None:
        config = _make_fixture_config(mcp_servers=[])
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe)
            assert not (Path(td) / ".mcp.json").exists()

    def test_no_permissions_when_empty(self) -> None:
        config = _make_fixture_config(permissions=Permissions(data={}))
        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe)
            assert not (Path(td) / ".claude" / "settings.json").exists()

    def test_yaml_round_trip_to_render(self) -> None:
        original = _make_fixture_config()
        yaml_text = original.to_yaml()
        restored = WorkenvConfig.from_yaml(yaml_text)
        assert original == restored

        recipe = load_recipe("claude")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), restored, recipe)
            assert (Path(td) / "CLAUDE.md").exists()
