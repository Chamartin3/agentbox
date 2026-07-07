"""Tests for the generator render function — OpenCode recipe."""

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
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.engines.backends.recipe_loader import list_recipes, load_recipe, backend_for_engine


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
        ],
        "resources": [ResourceRef(id="res-1")],
        "skills": [ResourceRef(id="skill-1")],
        "mcp_servers": [
            McpRef(
                name="my-mcp",
                config={"url": "http://localhost:8080", "transport": "http"},
            ),
        ],
        "permissions": Permissions(
            data={"allow": ["Read", "Write"], "deny": ["Bash"]}
        ),
        "env": {"KEY": "VAL"},
    }
    kwargs.update(overrides)
    return WorkspaceConfig(**kwargs)


class TestRecipeDiscovered:
    def test_opencode_is_listed(self) -> None:
        recipes = list_recipes()
        assert "opencode" in recipes

    def test_load_opencode_recipe(self) -> None:
        recipe = load_recipe("opencode")
        assert recipe.engine == "opencode"


class TestRenderOpenCode:
    def test_render_minimal(self) -> None:
        config = WorkspaceConfig(name="minimal")
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            result = render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))
            assert result.target_dir == Path(td)
            assert len(result.written_paths) >= 1

            oc_json = Path(td) / "opencode.json"
            assert oc_json.exists()
            data = json.loads(oc_json.read_text())
            assert data["$schema"] == "https://opencode.ai/config.json"

    def test_render_full(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))

            oc_json = Path(td) / "opencode.json"
            assert oc_json.exists()
            data = json.loads(oc_json.read_text())
            assert data["$schema"] == "https://opencode.ai/config.json"
            assert data["theme"] == "dracula"
            assert data["tools"] == {"skill": True}
            assert data["permission"] == {"*": "allow"}
            assert "main-agent" in data["agent"]
            assert data["agent"]["main-agent"]["description"] == ""
            assert "my-mcp" in data["mcp"]
            assert data["mcp"]["my-mcp"]["type"] == "remote"
            assert data["mcp"]["my-mcp"]["url"] == "http://localhost:8080"
            assert data["mcp"]["my-mcp"]["enabled"] is True

    def test_render_subagents(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))

            sub = Path(td) / ".opencode" / "agents" / "sub-1.md"
            assert sub.exists()
            content = sub.read_text()
            assert "description:" in content
            assert "skill_list: true" in content

    def test_render_main_agent_not_a_subagent_file(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))

            main_agent_file = Path(td) / "agents" / "main-agent.md"
            assert not main_agent_file.exists()

    def test_render_no_mcp_when_empty(self) -> None:
        config = _make_fixture_config(mcp_servers=[])
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))

            oc_json = Path(td) / "opencode.json"
            data = json.loads(oc_json.read_text())
            assert data.get("mcp") == {}

    def test_render_no_agents_in_json(self) -> None:
        config = WorkspaceConfig(name="no-agents")
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))

            oc_json = Path(td) / "opencode.json"
            data = json.loads(oc_json.read_text())
            assert data["agent"] == {}

    def test_idempotent(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("opencode")
        extra = _get_extra_items("opencode", config)
        with tempfile.TemporaryDirectory() as td:
            result1 = render(Path(td), config, recipe, extra_items=extra)
            result2 = render(Path(td), config, recipe, extra_items=extra)
            assert len(result1.written_paths) == len(result2.written_paths)

    def test_no_claude_files_written(self) -> None:
        config = _make_fixture_config()
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))

            assert not (Path(td) / "CLAUDE.md").exists()
            assert not (Path(td) / ".mcp.json").exists()
            assert not (Path(td) / ".claude").exists()

    def test_mcp_local_command(self) -> None:
        config = WorkspaceConfig(
            name="local-mcp",
            mcp_servers=[
                McpRef(
                    name="my-mcp",
                    config={"command": ["uvx", "my-server"], "transport": "stdio"},
                ),
            ],
        )
        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), config, recipe, extra_items=_get_extra_items("opencode", config))

            oc_json = Path(td) / "opencode.json"
            data = json.loads(oc_json.read_text())
            assert "my-mcp" in data["mcp"]
            assert data["mcp"]["my-mcp"]["type"] == "local"
            assert data["mcp"]["my-mcp"]["command"] == ["uvx", "my-server"]

    def test_yaml_round_trip_to_render(self) -> None:
        original = _make_fixture_config()
        yaml_text = original.to_yaml()
        restored = WorkspaceConfig.from_yaml(yaml_text)
        assert original == restored

        recipe = load_recipe("opencode")
        with tempfile.TemporaryDirectory() as td:
            render(Path(td), restored, recipe, extra_items=_get_extra_items("opencode", restored))
            assert (Path(td) / "opencode.json").exists()
