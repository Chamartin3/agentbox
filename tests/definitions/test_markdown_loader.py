"""Tests for markdown frontmatter agent loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data.manifest import AgentSource
from agentbox.core.deprecated.definitions.markdown import load_markdown_agent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_basic_frontmatter_and_body(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents.d" / "writer.md",
        """\
---
id: writer
description: Writes draft content
workspace: default
tools:
  - "@jobpost.read"
  - "@cv.write"
---
You are a helpful writing assistant.
""",
    )
    agent = load_markdown_agent(tmp_path / "agents.d" / "writer.md")
    assert agent.id == "writer"
    assert agent.description == "Writes draft content"
    assert agent.workspace == "default"
    assert agent.tools == ["@jobpost.read", "@cv.write"]
    assert agent.prompt == "You are a helpful writing assistant."
    assert agent.source_format == AgentSource.MARKDOWN
    assert agent.source_path == tmp_path / "agents.d" / "writer.md"


def test_missing_id_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "bad.md",
        """\
---
description: no id here
---
body
""",
    )
    with pytest.raises(ValueError, match="must contain a string 'id'"):
        load_markdown_agent(tmp_path / "bad.md")


def test_runner_fields_parsed(tmp_path: Path) -> None:
    _write(
        tmp_path / "claude.md",
        """\
---
id: claude-writer
runner:
  model: sonnet
  timeout_seconds: 300
  allowed_tools:
    - Read
    - Write
---
You are Claude.
""",
    )
    agent = load_markdown_agent(tmp_path / "claude.md")
    assert agent.runner.model == "sonnet"
    assert agent.runner.timeout_seconds == 300
    assert agent.runner.allowed_tools == ["Read", "Write"]


def test_tags_and_session_mode(tmp_path: Path) -> None:
    _write(
        tmp_path / "tagged.md",
        """\
---
id: tagged-agent
tags:
  - research
  - draft
session_mode: persistent
---
Body.
""",
    )
    agent = load_markdown_agent(tmp_path / "tagged.md")
    assert agent.tags == ["research", "draft"]
    assert agent.session_mode == "persistent"


def test_claude_agent_false(tmp_path: Path) -> None:
    _write(
        tmp_path / "pydantic.md",
        """\
---
id: pydantic-only
claude_agent: false
---
Pydantic body.
""",
    )
    agent = load_markdown_agent(tmp_path / "pydantic.md")
    assert agent.claude_agent is False


def test_headless_true(tmp_path: Path) -> None:
    _write(
        tmp_path / "headless.md",
        """\
---
id: headless-agent
headless: true
---
Headless body.
""",
    )
    agent = load_markdown_agent(tmp_path / "headless.md")
    assert agent.headless is True


def test_webhook_url(tmp_path: Path) -> None:
    _write(
        tmp_path / "webhook.md",
        """\
---
id: webhook-agent
webhook_url: https://example.com/hook
---
Body.
""",
    )
    agent = load_markdown_agent(tmp_path / "webhook.md")
    assert agent.webhook_url == "https://example.com/hook"


def test_unsupported_backends(tmp_path: Path) -> None:
    _write(
        tmp_path / "no-claude.md",
        """\
---
id: no-claude
unsupported_backends:
  - claude_code
---
Body.
""",
    )
    agent = load_markdown_agent(tmp_path / "no-claude.md")
    assert "claude_code" in agent.unsupported_backends


def test_load_markdown_with_inline_prompt_in_meta(tmp_path: Path) -> None:
    """If meta has a 'prompt' key, it takes precedence over body."""
    _write(
        tmp_path / "meta-prompt.md",
        """\
---
id: meta-prompt
prompt: This is from metadata
---
This is the body which should be ignored.
""",
    )
    agent = load_markdown_agent(tmp_path / "meta-prompt.md")
    assert agent.prompt == "This is from metadata"
