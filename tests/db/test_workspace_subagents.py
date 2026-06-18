"""Tests for workspace_subagents store methods (RESOURCES_PLAN E1/E2).

Exercises ``list_workspace_subagents`` and ``replace_workspace_subagents``
on ``SessionStore`` (via ``ResourceBindingsMixin``).
"""

from __future__ import annotations

import pytest


def test_replace_and_list_subagents(session_store) -> None:
    out = session_store.replace_workspace_subagents(
        "ws1",
        [
            {"agent_id": "agent-a", "alias": "researcher", "display_order": 0},
            {"agent_id": "agent-b", "alias": "writer", "display_order": 1},
        ],
        actor="tester",
    )
    assert [s["alias"] for s in out] == ["researcher", "writer"]

    listed = session_store.list_workspace_subagents("ws1")
    assert [s["alias"] for s in listed] == ["researcher", "writer"]
    assert [s["agent_id"] for s in listed] == ["agent-a", "agent-b"]
    assert all(s["workspace_id"] == "ws1" for s in listed)
    assert all(s.get("created_at") for s in listed)


def test_replace_clears_previous_rows(session_store) -> None:
    session_store.replace_workspace_subagents(
        "ws2",
        [
            {"agent_id": "a", "alias": "one"},
            {"agent_id": "b", "alias": "two"},
        ],
    )
    session_store.replace_workspace_subagents(
        "ws2",
        [{"agent_id": "c", "alias": "only"}],
    )
    listed = session_store.list_workspace_subagents("ws2")
    assert [s["alias"] for s in listed] == ["only"]
    assert listed[0]["agent_id"] == "c"


def test_duplicate_alias_in_payload_rejected(session_store) -> None:
    with pytest.raises(ValueError):
        session_store.replace_workspace_subagents(
            "ws3",
            [
                {"agent_id": "a", "alias": "dup"},
                {"agent_id": "b", "alias": "dup"},
            ],
        )


def test_missing_alias_rejected(session_store) -> None:
    with pytest.raises(ValueError):
        session_store.replace_workspace_subagents(
            "ws4",
            [{"agent_id": "a", "alias": ""}],
        )


def test_missing_agent_id_rejected(session_store) -> None:
    with pytest.raises(ValueError):
        session_store.replace_workspace_subagents(
            "ws5",
            [{"agent_id": "", "alias": "x"}],
        )


def test_list_isolated_per_workspace(session_store) -> None:
    session_store.replace_workspace_subagents(
        "wsA", [{"agent_id": "a", "alias": "alpha"}]
    )
    session_store.replace_workspace_subagents(
        "wsB", [{"agent_id": "b", "alias": "beta"}]
    )
    a = session_store.list_workspace_subagents("wsA")
    b = session_store.list_workspace_subagents("wsB")
    assert [s["alias"] for s in a] == ["alpha"]
    assert [s["alias"] for s in b] == ["beta"]
