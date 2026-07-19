"""Plan 122 enforcement: forbidden_tools removes native names from render.

A denied canonical tool must not survive into the backend's ``--allowedTools``
argv, while everything else the agent may use still renders.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.engines.backends.claude_code import ClaudeCodeBackend


def _agent_with_runtime(runtime: dict[str, list[str]]) -> AgentDef:
    agent = AgentDef(id="t.forbid", description="t", runner=RunnerSpec())
    agent.__dict__["_config_json"] = {"runtime": runtime}
    return agent


def _allowed_tools_argv(argv: list[str]) -> list[str]:
    """The tokens passed to --allowedTools (up to the next flag)."""
    if "--allowedTools" not in argv:
        return []
    out: list[str] = []
    for tok in argv[argv.index("--allowedTools") + 1 :]:
        if tok.startswith("--"):
            break
        out.append(tok)
    return out


def test_forbidden_tool_dropped_from_allow_list() -> None:
    agent = _agent_with_runtime(
        {
            "allowed_tools": ["fs.read", "fs.grep", "shell.exec"],
            "forbidden_tools": ["shell.exec"],
        }
    )
    rendered = ClaudeCodeBackend().render(agent, Path("/tmp/workdir"))
    allowed = _allowed_tools_argv(rendered.argv)
    assert "Bash" not in allowed  # native name of shell.exec
    assert "Read" in allowed
    assert "Grep" in allowed


def test_forbidden_only_materializes_available_minus_denied() -> None:
    # No allow-list: default is grant-all. Forbidding one tool must still
    # emit an explicit list (all native tools minus the denied one).
    agent = _agent_with_runtime({"forbidden_tools": ["shell.exec"]})
    rendered = ClaudeCodeBackend().render(agent, Path("/tmp/workdir"))
    allowed = _allowed_tools_argv(rendered.argv)
    assert allowed, "a deny-list must render an explicit --allowedTools"
    assert "Bash" not in allowed
    assert "Read" in allowed  # other native tools survive


def test_no_deny_list_is_unrestricted() -> None:
    # No allow-list and no deny-list → omit the flag (backend default = all).
    agent = _agent_with_runtime({})
    rendered = ClaudeCodeBackend().render(agent, Path("/tmp/workdir"))
    assert "--allowedTools" not in rendered.argv
