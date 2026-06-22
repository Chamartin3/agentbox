"""Shared fixtures for the workspace-generation render tests.

The Claude and OpenCode render suites previously each carried an
identical ``_make_fixture_config`` builder. It lives here now as a single
factory fixture so both suites share one source of truth.
"""

from __future__ import annotations

import pytest

from agentbox.core.workspaces.generation.config import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkenvConfig,
)


@pytest.fixture
def make_workenv_config():
    """Factory returning a fully-populated ``WorkenvConfig``.

    Pass keyword overrides to swap any field (e.g.
    ``make_workenv_config(mcp_servers=[])``).
    """

    def _make(**overrides: object) -> WorkenvConfig:
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
                    config={"url": "http://localhost:8080", "transport": "http"},
                ),
            ],
            "permissions": Permissions(
                data={"allow": ["Read", "Write"], "deny": ["Bash"]}
            ),
            "env": {"KEY": "VAL"},
        }
        kwargs.update(overrides)
        return WorkenvConfig(**kwargs)

    return _make
