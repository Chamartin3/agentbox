"""DB overlay for workspace runtime permissions.

The overlay row sits over WorkspaceDef defaults from the manifest. Only
fields explicitly set in the overlay shadow the manifest; unset (NULL)
columns keep inheriting. capabilities.json on disk is no longer the
source of truth — it is a derived artifact.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.db.database import Database


def test_no_overlay_row_returns_none(tmp_path: Path) -> None:
    store = Database(tmp_path / "agentbox.db")
    assert store.workspace_runtime_permissions.get_for_workspace("default") is None


def test_set_then_get_roundtrips_all_fields(tmp_path: Path) -> None:
    store = Database(tmp_path / "agentbox.db")
    store.workspace_runtime_permissions.set_for_workspace(
        "default",
        allowed_builtin_tools=["WebFetch", "AskUserQuestion"],
        files=[{"src": "shared/notes.md", "dst": "notes.md"}],
        max_tokens=32000,
        allow_file_write=False,
        allow_network=True,
    )
    row = store.workspace_runtime_permissions.get_for_workspace("default")
    assert row is not None
    assert row["allowed_builtin_tools"] == ["WebFetch", "AskUserQuestion"]
    assert row["files"] == [{"src": "shared/notes.md", "dst": "notes.md"}]
    assert row["max_tokens"] == 32000
    # SQLite stores booleans as 0/1 — the mixin normalizes on write.
    assert row["allow_file_write"] == 0
    assert row["allow_network"] == 1


def test_partial_update_preserves_unset_fields(tmp_path: Path) -> None:
    store = Database(tmp_path / "agentbox.db")
    store.workspace_runtime_permissions.set_for_workspace(
        "default",
        allowed_builtin_tools=["WebFetch"],
        max_tokens=16000,
    )
    # Only update max_tokens; built-in tools list must survive.
    store.workspace_runtime_permissions.set_for_workspace("default", max_tokens=64000)
    row = store.workspace_runtime_permissions.get_for_workspace("default")
    assert row is not None
    assert row["max_tokens"] == 64000
    assert row["allowed_builtin_tools"] == ["WebFetch"]


def test_unset_field_means_inherit_from_manifest(tmp_path: Path) -> None:
    """A workspace with no overlay row inherits 100% from manifest defaults."""
    store = Database(tmp_path / "agentbox.db")
    # Confirmed by absence of any row — the route layer is responsible for
    # falling back to WorkspaceDef when get_workspace_runtime_permissions
    # returns None. This test pins that absence behavior.
    assert store.workspace_runtime_permissions.get_for_workspace("never-touched") is None
