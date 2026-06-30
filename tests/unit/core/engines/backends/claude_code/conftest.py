"""Fixtures for the Claude Code backend adapter tests.

Wraps the shared ``make_backend_agent`` factory (from ``backends/conftest.py``)
to also materialise the ``_config_json`` runtime shim the claude_code render
path falls back to, keyed off the agent's resolved runner.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from agentbox.core.data import AgentDef, RunnerSpec

DEFAULT_RUNNER = RunnerSpec(
    kind="claude_code",
    model="claude-sonnet-4-20250514",
    allowed_tools=["Read", "Grep", "Write"],
    extra_args=["--verbose"],
)


@pytest.fixture
def make_claude_agent(make_backend_agent) -> Callable[..., AgentDef]:
    """Factory for a claude_code AgentDef with its ``_config_json`` shim.

    Defaults ``runner=DEFAULT_RUNNER``; pass ``**overrides`` (e.g. a custom
    ``runner``) to customise. The ``_config_json`` runtime block is derived
    from the resolved runner so it stays in sync with overrides.
    """

    def _make(**overrides: object) -> AgentDef:
        overrides.setdefault("id", "test_agent")
        overrides.setdefault("runner", DEFAULT_RUNNER)
        agent = make_backend_agent(**overrides)
        agent.__dict__["_config_json"] = {
            "runtime": {
                "mcp_config_path": agent.runner.mcp_config_path,
                "allowed_tools": list(agent.runner.allowed_tools),
            },
        }
        return agent

    return _make
