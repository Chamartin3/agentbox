"""target_path uniqueness within a workspace's binding set."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.db import SessionStore


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


def _seed_resource(store: SessionStore, slug: str, rtype: str = "document") -> str:
    """Create a minimal resource and return its id."""
    row = store.create_repo_resource(slug=slug, type=rtype, display_name=slug)
    return row["id"]


def test_two_folder_bindings_with_same_target_path_raise(
    store: SessionStore, tmp_path: Path
) -> None:
    """Folder bindings collide because their target_path IS the directory."""
    r1 = _seed_resource(store, "folder.one", rtype="folder")
    r2 = _seed_resource(store, "folder.two", rtype="folder")

    with pytest.raises(ValueError, match="must be unique"):
        store.replace_workspace_file_bindings(
            "ws",
            [
                {"resource_id": r1, "target_path": "shared"},
                {"resource_id": r2, "target_path": "shared"},
            ],
            reason="dup folders",
        )


def test_two_documents_with_same_target_path_are_allowed(
    store: SessionStore, tmp_path: Path
) -> None:
    """Document bindings with the same target_path resolve to different
    filenames inside it — no collision."""
    r1 = _seed_resource(store, "doc.one")
    r2 = _seed_resource(store, "doc.two")

    items = store.replace_workspace_file_bindings(
        "ws",
        [
            {"resource_id": r1, "target_path": "docs"},
            {"resource_id": r2, "target_path": "docs"},
        ],
        reason="two docs in same folder",
    )
    assert len(items) == 2


def test_multiple_null_target_paths_are_allowed(
    store: SessionStore, tmp_path: Path
) -> None:
    """Null target_path is allowed in multiple bindings — each resolves
    its own filename from the resource."""
    r1 = _seed_resource(store, "doc.three")
    r2 = _seed_resource(store, "doc.four")

    items = store.replace_workspace_file_bindings(
        "ws",
        [
            {"resource_id": r1, "target_path": None},
            {"resource_id": r2, "target_path": None},
        ],
        reason="null targets ok",
    )
    assert len(items) == 2


def test_folder_target_trailing_slash_normalized(
    store: SessionStore, tmp_path: Path
) -> None:
    """'shared' and 'shared/' on two folder bindings collide."""
    r1 = _seed_resource(store, "folder.three", rtype="folder")
    r2 = _seed_resource(store, "folder.four", rtype="folder")

    with pytest.raises(ValueError, match="must be unique"):
        store.replace_workspace_file_bindings(
            "ws",
            [
                {"resource_id": r1, "target_path": "shared"},
                {"resource_id": r2, "target_path": "shared/"},
            ],
            reason="trailing slash",
        )
