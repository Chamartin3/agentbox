"""Tests for env-doc rendering (CLAUDE.md / AGENTS.md)."""

from __future__ import annotations

from agentbox.core.workspaces.env_doc.renderers.agents_md import AgentsMdRenderer
from agentbox.core.workspaces.env_doc.renderers.base import (
    ReferenceEntry,
    RuntimeContext,
    _render_body,
    _visible_for,
)
from agentbox.core.workspaces.env_doc.renderers.claude_md import ClaudeMdRenderer
from agentbox.core.workspaces.env_doc.schema import (
    Command,
    EnvDocContent,
    References,
    Section,
)


def _minimal_content() -> EnvDocContent:
    return EnvDocContent(
        project_name="Test Project",
        overview="A test project overview.",
    )


class TestVisibility:
    def test_hidden_always_false(self) -> None:
        section = Section(id="hidden", title="Hidden", body_markdown="x", visibility="hidden")
        assert _visible_for(section, "claude_only") is False
        assert _visible_for(section, "agents_only") is False

    def test_both_always_true(self) -> None:
        section = Section(id="shared", title="Shared", body_markdown="x", visibility="both")
        assert _visible_for(section, "claude_only") is True
        assert _visible_for(section, "agents_only") is True

    def test_audience_match(self) -> None:
        section = Section(id="claude", title="Claude", body_markdown="x", visibility="claude_only")
        assert _visible_for(section, "claude_only") is True
        assert _visible_for(section, "agents_only") is False


class TestRenderBody:
    def test_project_name_and_overview(self) -> None:
        result = _render_body(_minimal_content(), RuntimeContext(), "both")
        assert "# Test Project" in result
        assert "A test project overview." in result

    def test_conventions_section(self) -> None:
        content = EnvDocContent(
            project_name="P",
            overview="O",
            conventions=["Use tabs", "No trailing whitespace"],
        )
        result = _render_body(content, RuntimeContext(), "both")
        assert "## Conventions" in result
        assert "- Use tabs" in result
        assert "- No trailing whitespace" in result

    def test_commands_table(self) -> None:
        content = EnvDocContent(
            project_name="P",
            overview="O",
            commands=[Command(label="test", command="pytest", description="Run tests")],
        )
        result = _render_body(content, RuntimeContext(), "both")
        assert "## Commands" in result
        assert "pytest" in result
        assert "Run tests" in result

    def test_sections_filtered_by_visibility(self) -> None:
        content = EnvDocContent(
            project_name="P",
            overview="O",
            sections=[
                Section(id="claude_only", title="Claude Only", body_markdown="claude", visibility="claude_only"),
                Section(id="agents_only", title="Agents Only", body_markdown="agents", visibility="agents_only"),
            ],
        )
        claude_result = _render_body(content, RuntimeContext(), "claude_only")
        assert "Claude Only" in claude_result
        assert "Agents Only" not in claude_result

        agents_result = _render_body(content, RuntimeContext(), "agents_only")
        assert "Agents Only" in agents_result
        assert "Claude Only" not in agents_result

    def test_references_section(self) -> None:
        content = EnvDocContent(
            project_name="P",
            overview="O",
            references=References(
                include_skills=True,
                custom_links=[{"label": "API Docs", "url": "https://docs.example.com"}],
            ),
        )
        ctx = RuntimeContext(
            skills=[ReferenceEntry(label="web-dev", detail="Web development tools")],
        )
        result = _render_body(content, ctx, "both")
        assert "## Resources available" in result
        assert "web-dev" in result
        assert "API Docs" in result

    def test_layout_section(self) -> None:
        content = EnvDocContent(
            project_name="P",
            overview="O",
            working_directory_layout="src/\n  components/",
        )
        result = _render_body(content, RuntimeContext(), "both")
        assert "## Working directory layout" in result

    def test_ends_with_newline(self) -> None:
        result = _render_body(_minimal_content(), RuntimeContext(), "both")
        assert result.endswith("\n")


class TestClaudeMdRenderer:
    def test_renders_with_claude_audience(self) -> None:
        renderer = ClaudeMdRenderer()
        content = EnvDocContent(
            project_name="C",
            overview="claude project",
            sections=[Section(id="secret", title="Secret", body_markdown="claude only", visibility="claude_only")],
        )
        result = renderer.render(content, RuntimeContext())
        assert "claude project" in result
        assert "Secret" in result


class TestAgentsMdRenderer:
    def test_renders_with_agents_audience(self) -> None:
        renderer = AgentsMdRenderer()
        content = EnvDocContent(
            project_name="A",
            overview="agents project",
            sections=[Section(id="secret", title="Secret", body_markdown="agents only", visibility="agents_only")],
        )
        result = renderer.render(content, RuntimeContext())
        assert "agents project" in result
        assert "Secret" in result
