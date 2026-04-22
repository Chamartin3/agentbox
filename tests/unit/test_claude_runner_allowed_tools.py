"""Effective allow list = agent.allowed_tools ∩ workspace.allowed_tools.

If either side is empty, treat it as "no restriction" so the other governs.
This makes the common case — agent declares its tools, workspace adds no
further restriction — behave intuitively, while still allowing the workspace
to narrow the set when desired.
"""

from __future__ import annotations

from agentbox.core.runners.claude_code import _intersect_allowed_tools


def test_both_empty_returns_empty() -> None:
    assert _intersect_allowed_tools([], None) == []
    assert _intersect_allowed_tools([], []) == []


def test_agent_only_passes_through() -> None:
    assert _intersect_allowed_tools(["Read", "Grep"], None) == ["Read", "Grep"]
    assert _intersect_allowed_tools(["Read", "Grep"], []) == ["Read", "Grep"]


def test_workspace_only_passes_through() -> None:
    assert _intersect_allowed_tools([], ["Read", "Write"]) == ["Read", "Write"]


def test_intersection_when_both_present() -> None:
    result = _intersect_allowed_tools(
        ["Read", "Grep", "Write"], ["Read", "Write", "Bash"]
    )
    assert set(result) == {"Read", "Write"}


def test_intersection_preserves_agent_order() -> None:
    # Agent order is meaningful (CLI args).
    result = _intersect_allowed_tools(
        ["Grep", "Read", "Write"], ["Write", "Read", "Bash"]
    )
    assert result == ["Read", "Write"]


def test_workspace_narrower_than_agent() -> None:
    # Workspace clamps the agent's allow list.
    result = _intersect_allowed_tools(
        ["Read", "Grep", "Write", "Bash"], ["Read"]
    )
    assert result == ["Read"]


def test_agent_narrower_than_workspace() -> None:
    result = _intersect_allowed_tools(["Read"], ["Read", "Grep", "Write"])
    assert result == ["Read"]


def test_disjoint_returns_empty() -> None:
    # Nothing in common — the runner gets an empty allow list and (by the
    # caller's check) skips --allowedTools entirely.
    assert _intersect_allowed_tools(["Read"], ["Bash"]) == []
