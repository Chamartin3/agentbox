"""Tests for EnvDocContent pydantic model."""

from __future__ import annotations


from agentbox.core.workspaces.env_doc.schema import (
    Command,
    CustomLink,
    EnvDocContent,
    References,
    Section,
)


class TestEnvDocContent:
    def test_minimal_construction(self) -> None:
        content = EnvDocContent(project_name="Test", overview="A test project")
        assert content.project_name == "Test"
        assert content.overview == "A test project"
        assert content.working_directory_layout is None
        assert content.conventions == []
        assert content.commands == []

    def test_project_name_defaults_to_empty(self) -> None:
        content = EnvDocContent(overview="No name")
        assert content.project_name == ""

    def test_full_construction(self) -> None:
        content = EnvDocContent(
            project_name="Full",
            overview="Overview",
            working_directory_layout="src/",
            conventions=["Use tabs"],
            commands=[Command(label="test", command="pytest", description="Run tests")],
            verification=["Run tests"],
            sections=[Section(id="e", title="Extra", body_markdown="content")],
            references=References(include_skills=True),
        )
        assert content.conventions == ["Use tabs"]
        assert len(content.commands) == 1
        assert content.commands[0].label == "test"

    def test_sections_default_to_visible(self) -> None:
        content = EnvDocContent(
            project_name="P",
            overview="O",
            sections=[Section(id="d", title="Default", body_markdown="x")],
        )
        assert content.sections[0].visibility == "both"


class TestCommand:
    def test_minimal(self) -> None:
        cmd = Command(label="build", command="npm run build")
        assert cmd.label == "build"
        assert cmd.command == "npm run build"
        assert cmd.description == ""


class TestCustomLink:
    def test_minimal(self) -> None:
        link = CustomLink(label="API", url="https://api.example.com")
        assert link.label == "API"
        assert link.url == "https://api.example.com"
