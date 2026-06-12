"""Tests for Recipe loading."""

from __future__ import annotations

from agentbox.core.workspaces.generation.recipe import list_recipes, load_recipe


class TestRecipe:
    def test_list_recipes(self) -> None:
        recipes = list_recipes()
        assert "claude" in recipes

    def test_load_claude_recipe(self) -> None:
        recipe = load_recipe("claude")
        assert recipe.engine == "claude"
        assert recipe.layout["context"] == "CLAUDE.md"
        assert recipe.layout["subagent"] == ".claude/agents/{name}.md"
        assert recipe.layout["mcp_config"] == ".mcp.json"
        assert recipe.layout["permissions"] == ".claude/settings.json"
        assert recipe.serialization["mcp_config"] == "json"
        assert recipe.serialization["permissions"] == "json"
        assert recipe.templates["context"] == "templates/context.md.tmpl"
        assert recipe.templates["subagent"] == "templates/subagent.md.tmpl"

    def test_resolve_layout(self) -> None:
        recipe = load_recipe("claude")
        assert recipe.resolve_layout("context") == "CLAUDE.md"
        assert (
            recipe.resolve_layout("subagent", name="my-agent")
            == ".claude/agents/my-agent.md"
        )

    def test_resolve_template(self) -> None:
        recipe = load_recipe("claude")
        ctx_tmpl = recipe.resolve_template("context")
        assert ctx_tmpl is not None
        assert "$name" in ctx_tmpl
        assert "$description" in ctx_tmpl

        sub_tmpl = recipe.resolve_template("subagent")
        assert sub_tmpl is not None
        assert "$name" in sub_tmpl

    def test_resolve_template_missing_role(self) -> None:
        recipe = load_recipe("claude")
        assert recipe.resolve_template("nonexistent") is None

    def test_load_nonexistent_recipe(self) -> None:
        import pytest
        with pytest.raises(FileNotFoundError):
            load_recipe("nonexistent")

    def test_recipe_frozen(self) -> None:
        recipe = load_recipe("claude")
        import pytest
        with pytest.raises(Exception):
            recipe.engine = "other"  # type: ignore[misc]
