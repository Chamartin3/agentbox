"""Effective allow list = agent.allowed_tools ∩ workspace.allowed_tools.

If either side is empty, treat it as "no restriction" so the other governs.
This makes the common case — agent declares its tools, workspace adds no
further restriction — behave intuitively, while still allowing the workspace
to narrow the set when desired.
"""

from __future__ import annotations

from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.translation import intersect_allowed_tools

_READ = CanonicalTool.FS_READ
_WRITE = CanonicalTool.FS_WRITE
_GREP = CanonicalTool.FS_GREP
_BASH = CanonicalTool.SHELL_EXEC


def test_both_empty_returns_empty() -> None:
    assert intersect_allowed_tools(set(), None) == set()
    assert intersect_allowed_tools(set(), set()) == set()


def test_agent_only_passes_through() -> None:
    assert intersect_allowed_tools({_READ, _GREP}, None) == {_READ, _GREP}
    assert intersect_allowed_tools({_READ, _GREP}, set()) == {_READ, _GREP}


def test_workspace_only_passes_through() -> None:
    assert intersect_allowed_tools(set(), {_READ, _WRITE}) == {_READ, _WRITE}


def test_intersection_when_both_present() -> None:
    result = intersect_allowed_tools(
        {_READ, _GREP, _WRITE}, {_READ, _WRITE, _BASH}
    )
    assert result == {_READ, _WRITE}


def test_workspace_narrower_than_agent() -> None:
    # Workspace clamps the agent's allow list.
    result = intersect_allowed_tools({_READ, _GREP, _WRITE, _BASH}, {_READ})
    assert result == {_READ}


def test_agent_narrower_than_workspace() -> None:
    result = intersect_allowed_tools({_READ}, {_READ, _GREP, _WRITE})
    assert result == {_READ}


def test_disjoint_returns_empty() -> None:
    # Nothing in common — the runner gets an empty set.
    assert intersect_allowed_tools({_READ}, {_BASH}) == set()
