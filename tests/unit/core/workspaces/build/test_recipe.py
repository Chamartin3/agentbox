"""Tests for Recipe loading."""

from __future__ import annotations

import pytest
from agentbox.core.engines.backends.recipe_loader import list_recipes, load_recipe


class TestRecipe:
    def test_list_recipes(self) -> None:
        recipes = list_recipes()
        assert "claude_code" in recipes

    def test_load_claude_recipe(self) -> None:
        recipe = load_recipe("claude_code")
        assert recipe.engine == "claude_code"
        assert recipe.layout["context"] == "CLAUDE.md"
        assert recipe.layout["subagent"] == ".claude/agents/{name}.md"
        assert recipe.layout["mcp_config"] == ".mcp.json"
        assert recipe.layout["permissions"] == ".claude/settings.json"
        assert recipe.serialization["mcp_config"] == "json"
        assert recipe.serialization["permissions"] == "json"
        assert recipe.templates["subagent"] == "templates/subagent.md.tmpl"

    def test_resolve_layout(self) -> None:
        recipe = load_recipe("claude_code")
        assert recipe.resolve_layout("context") == "CLAUDE.md"
        assert (
            recipe.resolve_layout("subagent", name="my-agent")
            == ".claude/agents/my-agent.md"
        )

    def test_resolve_template(self) -> None:
        recipe = load_recipe("claude_code")
        sub_tmpl = recipe.resolve_template("subagent")
        assert sub_tmpl is not None
        assert "$name" in sub_tmpl

    def test_resolve_template_missing_role(self) -> None:
        recipe = load_recipe("claude_code")
        assert recipe.resolve_template("nonexistent") is None

    def test_load_nonexistent_recipe(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_recipe("nonexistent")

    def test_recipe_frozen(self) -> None:
        recipe = load_recipe("claude_code")
        with pytest.raises(Exception):
            recipe.engine = "other"  # type: ignore[misc]
