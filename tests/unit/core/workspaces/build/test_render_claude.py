"""Tests for the generator render function — Claude recipe."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agentbox.core.data.workenv import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkspaceConfig,
)
from agentbox.core.workspaces.build.engine import render
from agentbox.core.engines.backends.recipe_loader import load_recipe, backend_for_engine


def _get_extra_items(engine: str, config: WorkspaceConfig) -> list:
    """Helper to get extra_items for rendering."""
    try:
        return backend_for_engine(engine).build_workspace_items(config)
    except KeyError:
        return []


def _make_fixture_config(**overrides: object) -> WorkspaceConfig:
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
    return WorkspaceConfig(**kwargs)


class TestRenderClaude:
    def test_render_minimal(self) -> None:
        config = WorkspaceConfig(name="minimal")
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            result = render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))
            assert result.target_dir == Path(td)
            assert len(result.written_paths) >= 1

            claude_md = Path(td) / "CLAUDE.md"
            assert claude_md.exists()

    def test_render_full(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))

            claude_md = Path(td) / "CLAUDE.md"
            assert claude_md.exists()
            content = claude_md.read_text()
            # CLAUDE.md is the raw env-doc body (no context template).
            assert "env doc" in content

    def test_render_subagents(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))

            sub1 = Path(td) / ".claude" / "agents" / "sub-1.md"
            sub2 = Path(td) / ".claude" / "agents" / "sub-2.md"
            assert sub1.exists()
            assert sub2.exists()
            assert "sub-1" in sub1.read_text()

    def test_subagent_carries_description_and_prompt(self) -> None:
        # Native .claude/agents/*.md must hold real content, not empty
        # placeholders — the format the Claude engine reads.
        config = WorkspaceConfig(
            name="ws",
            agents=[
                AgentRef(
                    id="sub-1",
                    role="subagent",
                    description="does the thing",
                    prompt="You are a careful worker.",
                )
            ],
        )
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))
            text = (Path(td) / ".claude" / "agents" / "sub-1.md").read_text()
            assert 'description: "does the thing"' in text
            assert "You are a careful worker." in text

    def test_render_main_agent_not_a_subagent(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))

            main_agent_file = Path(td) / ".claude" / "agents" / "main-agent.md"
            assert not main_agent_file.exists()

    def test_render_mcp_config(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))

            mcp_file = Path(td) / ".mcp.json"
            assert mcp_file.exists()
            mcp_data = json.loads(mcp_file.read_text())
            assert "mcpServers" in mcp_data
            assert "my-mcp" in mcp_data["mcpServers"]
            assert (
                mcp_data["mcpServers"]["my-mcp"]["url"]
                == "http://localhost:8080"
            )

    def test_render_mcp_config_disabled_tools(self) -> None:
        """Per-server disabled_tools emit the claude_code-native tools.exclude block."""
        config = _make_fixture_config(
            mcp_servers=[
                McpRef(
                    name="time-server",
                    config={"url": "http://localhost:8080"},
                    disabled_tools=["convert_time"],
                ),
                McpRef(
                    name="filesystem",
                    config={"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
                    disabled_tools=["write_file", "create_directory"],
                ),
            ],
        )
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))

            mcp_file = Path(td) / ".mcp.json"
            assert mcp_file.exists()
            mcp_data = json.loads(mcp_file.read_text())

            time_srv = mcp_data["mcpServers"]["time-server"]
            assert "tools" in time_srv
            assert time_srv["tools"]["exclude"] == ["convert_time"]

            fs_srv = mcp_data["mcpServers"]["filesystem"]
            assert "tools" in fs_srv
            assert fs_srv["tools"]["exclude"] == [
                "create_directory",
                "write_file",
            ]

    def test_render_mcp_config_no_tools_when_empty_disabled(self) -> None:
        """No tools key is emitted when disabled_tools is empty."""
        config = _make_fixture_config(
            mcp_servers=[
                McpRef(
                    name="time-server",
                    config={"url": "http://localhost:8080"},
                    disabled_tools=[],
                ),
            ],
        )
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))

            mcp_file = Path(td) / ".mcp.json"
            mcp_data = json.loads(mcp_file.read_text())
            time_srv = mcp_data["mcpServers"]["time-server"]
            assert "tools" not in time_srv

    def test_render_permissions(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))

            perm_file = Path(td) / ".claude" / "settings.json"
            assert perm_file.exists()
            perm_data = json.loads(perm_file.read_text())
            assert "permissions" in perm_data
            assert perm_data["permissions"]["allow"] == ["Read", "Write"]

    def test_idempotent(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("claude_code")
        extra = _get_extra_items("claude_code", config)
        with tempfile.TemporaryDirectory() as td:
            result1 = render(Path(td), config, recipe, extra_items=extra)
            result2 = render(Path(td), config, recipe, extra_items=extra)
            assert len(result1.written_paths) == len(result2.written_paths)

    def test_no_mcp_when_empty(self) -> None:
        config = _make_fixture_config(mcp_servers=[])
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))
            assert not (Path(td) / ".mcp.json").exists()

    def test_no_permissions_when_empty(self) -> None:
        config = _make_fixture_config(permissions=Permissions(data={}))
        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("claude_code", config))
            assert not (Path(td) / ".claude" / "settings.json").exists()

    def test_yaml_round_trip_to_render(self) -> None:
        original = _make_fixture_config()
        yaml_text = original.to_yaml()
        restored = WorkspaceConfig.from_yaml(yaml_text)
        assert original == restored

        recipe = load_recipe("claude_code")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), restored, recipe)
            assert (Path(td) / "CLAUDE.md").exists()
