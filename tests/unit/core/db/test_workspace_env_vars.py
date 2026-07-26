"""WorkspaceEnvVarManager — round-trip + validation tests."""
from __future__ import annotations

from agentbox.core.db.database import Database


def test_list_empty(db: Database) -> None:
    """No env vars → empty dict."""
    mgr = db.workspace_env_vars
    assert mgr.list_for_workspace("ws-nonexistent") == {}


def test_replace_and_list(db: Database) -> None:
    """replace_for_workspace round-trips through list_for_workspace."""
    mgr = db.workspace_env_vars
    ws = "ws-env-roundtrip"

    result = mgr.replace_for_workspace(ws, {"FOO": "bar", "BAZ": "qux"})
    assert result == {"BAZ": "qux", "FOO": "bar"}

    loaded = mgr.list_for_workspace(ws)
    assert loaded == {"BAZ": "qux", "FOO": "bar"}


def test_replace_overwrites(db: Database) -> None:
    """Subsequent replace_for_workspace replaces the full set."""
    mgr = db.workspace_env_vars
    ws = "ws-env-overwrite"

    mgr.replace_for_workspace(ws, {"A": "1", "B": "2"})
    mgr.replace_for_workspace(ws, {"C": "3"})

    assert mgr.list_for_workspace(ws) == {"C": "3"}


def test_replace_clear(db: Database) -> None:
    """Replace with empty dict clears all vars."""
    mgr = db.workspace_env_vars
    ws = "ws-env-clear"

    mgr.replace_for_workspace(ws, {"X": "y"})
    mgr.replace_for_workspace(ws, {})

    assert mgr.list_for_workspace(ws) == {}


def test_delete_for_workspace(db: Database) -> None:
    """delete_for_workspace removes all entries."""
    mgr = db.workspace_env_vars
    ws = "ws-env-delete"

    mgr.replace_for_workspace(ws, {"K1": "v1", "K2": "v2"})
    mgr.delete_for_workspace(ws)

    assert mgr.list_for_workspace(ws) == {}


def test_delete_idempotent(db: Database) -> None:
    """delete_for_workspace on a non-existent workspace is safe."""
    mgr = db.workspace_env_vars
    mgr.delete_for_workspace("ws-never-existed")
    # Should not raise


def test_isolation_across_workspaces(db: Database) -> None:
    """Vars are isolated per workspace."""
    mgr = db.workspace_env_vars

    mgr.replace_for_workspace("ws-a", {"A": "1"})
    mgr.replace_for_workspace("ws-b", {"B": "2"})

    assert mgr.list_for_workspace("ws-a") == {"A": "1"}
    assert mgr.list_for_workspace("ws-b") == {"B": "2"}
