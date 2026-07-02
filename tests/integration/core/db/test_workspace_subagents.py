"""Tests for workspace_subagents store methods (RESOURCES_PLAN E1/E2).

Exercises ``list_workspace_subagents`` and ``replace_workspace_subagents``
on ``SessionStore`` (via ``ResourceBindingsMixin``).
"""

from __future__ import annotations

import pytest

from agentbox.core.db import WorkspaceSubagentManager


def test_replace_and_list_subagents(workspace_subagents: WorkspaceSubagentManager) -> None:
    out = workspace_subagents.replace_for_workspace(
        "ws1",
        [
            {"agent_id": "agent-a", "alias": "researcher", "display_order": 0},
            {"agent_id": "agent-b", "alias": "writer", "display_order": 1},
        ],
        actor="tester",
    )
    assert [s["alias"] for s in out] == ["researcher", "writer"]

    listed = workspace_subagents.list_for_workspace("ws1")
    assert [s["alias"] for s in listed] == ["researcher", "writer"]
    assert [s["agent_id"] for s in listed] == ["agent-a", "agent-b"]
    assert all(s["workspace_id"] == "ws1" for s in listed)
    assert all(s.get("created_at") for s in listed)


def test_replace_clears_previous_rows(workspace_subagents: WorkspaceSubagentManager) -> None:
    workspace_subagents.replace_for_workspace(
        "ws2",
        [
            {"agent_id": "a", "alias": "one"},
            {"agent_id": "b", "alias": "two"},
        ],
    )
    workspace_subagents.replace_for_workspace(
        "ws2",
        [{"agent_id": "c", "alias": "only"}],
    )
    listed = workspace_subagents.list_for_workspace("ws2")
    assert [s["alias"] for s in listed] == ["only"]
    assert listed[0]["agent_id"] == "c"


def test_duplicate_alias_in_payload_rejected(workspace_subagents: WorkspaceSubagentManager) -> None:
    with pytest.raises(ValueError):
        workspace_subagents.replace_for_workspace(
            "ws3",
            [
                {"agent_id": "a", "alias": "dup"},
                {"agent_id": "b", "alias": "dup"},
            ],
        )


def test_missing_alias_rejected(workspace_subagents: WorkspaceSubagentManager) -> None:
    with pytest.raises(ValueError):
        workspace_subagents.replace_for_workspace(
            "ws4",
            [{"agent_id": "a", "alias": ""}],
        )


def test_missing_agent_id_rejected(workspace_subagents: WorkspaceSubagentManager) -> None:
    with pytest.raises(ValueError):
        workspace_subagents.replace_for_workspace(
            "ws5",
            [{"agent_id": "", "alias": "x"}],
        )


def test_list_isolated_per_workspace(workspace_subagents: WorkspaceSubagentManager) -> None:
    workspace_subagents.replace_for_workspace(
        "wsA", [{"agent_id": "a", "alias": "alpha"}]
    )
    workspace_subagents.replace_for_workspace(
        "wsB", [{"agent_id": "b", "alias": "beta"}]
    )
    a = workspace_subagents.list_for_workspace("wsA")
    b = workspace_subagents.list_for_workspace("wsB")
    assert [s["alias"] for s in a] == ["alpha"]
    assert [s["alias"] for s in b] == ["beta"]
