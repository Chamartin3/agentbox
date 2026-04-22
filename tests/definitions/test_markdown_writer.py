"""Tests for markdown frontmatter agent writing and round-trip."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.constants import RunnerKind
from agentbox.core.data.manifest import AgentDef, AgentSource, RunnerSpec
from agentbox.core.definitions.markdown import load_markdown_agent, write_markdown_agent


def _round_trip(tmp_path: Path, agent: AgentDef) -> AgentDef:
    path = tmp_path / "roundtrip.md"
    write_markdown_agent(path, agent)
    return load_markdown_agent(path)


def test_round_trip_basic(tmp_path: Path) -> None:
    agent = AgentDef(
        id="test-agent",
        description="Test description",
        workspace="default",
        tools=["@read", "@write"],
        tags=["tag1"],
        runner=RunnerSpec(kind=RunnerKind.PYDANTIC_AI, timeout_seconds=120),
        prompt="Hello world",
        source_format=AgentSource.MARKDOWN,
        source_path=tmp_path / "test.md",
    )
    loaded = _round_trip(tmp_path, agent)
    assert loaded.id == "test-agent"
    assert loaded.description == "Test description"
    assert loaded.workspace == "default"
    assert loaded.tools == ["@read", "@write"]
    assert loaded.tags == ["tag1"]
    assert loaded.prompt == "Hello world"


def test_round_trip_runner_fields(tmp_path: Path) -> None:
    agent = AgentDef(
        id="claude-test",
        runner=RunnerSpec(
            kind=RunnerKind.CLAUDE_CODE,
            model="sonnet",
            timeout_seconds=300,
            allowed_tools=["Read", "Write"],
            extra_args=["--verbose"],
        ),
        prompt="You are Claude",
        source_format=AgentSource.MARKDOWN,
    )
    loaded = _round_trip(tmp_path, agent)
    assert loaded.runner.model == "sonnet"
    assert loaded.runner.timeout_seconds == 300


def test_round_trip_headless(tmp_path: Path) -> None:
    agent = AgentDef(
        id="headless",
        headless=True,
        runner=RunnerSpec(kind=RunnerKind.PYDANTIC_AI),
        prompt="Do JSON",
        source_format=AgentSource.MARKDOWN,
    )
    loaded = _round_trip(tmp_path, agent)
    assert loaded.headless is True


def test_round_trip_webhook(tmp_path: Path) -> None:
    agent = AgentDef(
        id="webhook",
        webhook_url="https://example.com/hook",
        runner=RunnerSpec(kind=RunnerKind.PYDANTIC_AI),
        prompt="Body",
        source_format=AgentSource.MARKDOWN,
    )
    loaded = _round_trip(tmp_path, agent)
    assert loaded.webhook_url == "https://example.com/hook"


def test_preserve_unknown_keys(tmp_path: Path) -> None:
    """Unknown frontmatter keys are preserved on write."""
    import frontmatter

    path = tmp_path / "unknown.md"
    path.write_text(
        """\
---
id: unknown-keys
x-custom: some-value
y-another: 42
---
Body
"""
    )
    agent = load_markdown_agent(path)
    assert agent.id == "unknown-keys"
    existing_metadata = dict(frontmatter.load(str(path)).metadata)
    # Write with preserve_unknown_keys=True
    write_markdown_agent(path, agent, preserve_unknown_keys=True, existing_metadata=existing_metadata)
    # Re-read and check unknown keys preserved
    content = path.read_text()
    assert "x-custom" in content
    assert "y-another" in content


def test_body_trailing_newline_normalized(tmp_path: Path) -> None:
    """Trailing whitespace is trimmed on write."""
    agent = AgentDef(
        id="trimmed",
        runner=RunnerSpec(kind=RunnerKind.PYDANTIC_AI),
        prompt="Some content\n\n",
        source_format=AgentSource.MARKDOWN,
    )
    path = tmp_path / "trimmed.md"
    write_markdown_agent(path, agent)
    content = path.read_text()
    assert not content.endswith("\n\n\n")
    # Should end with exactly one newline
    assert content.endswith("\n")


def test_empty_body_handled(tmp_path: Path) -> None:
    agent = AgentDef(
        id="no-body",
        runner=RunnerSpec(kind=RunnerKind.PYDANTIC_AI),
        source_format=AgentSource.MARKDOWN,
    )
    path = tmp_path / "no-body.md"
    write_markdown_agent(path, agent)
    loaded = load_markdown_agent(path)
    assert loaded.id == "no-body"
    assert loaded.prompt is None
