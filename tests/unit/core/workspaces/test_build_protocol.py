"""Plan 08 — verify build_workspace accepts a narrow WorkspaceBuildStore."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from agentbox.core.db import WorkspaceBuildStore
from agentbox.core.workspaces.build import build_workspace


def test_build_workspace_accepts_narrow_protocol(tmp_path):
    store = MagicMock(spec=WorkspaceBuildStore)
    store.get_workspace.return_value = {"id": "ws1", "path": str(tmp_path)}
    store.list_workspace_file_bindings.return_value = []
    store.list_workspace_subagents.return_value = []
    store.get_active_env_doc.return_value = None

    settings = SimpleNamespace(
        resource_cache_dir=tmp_path / "cache",
        project_root=tmp_path,
        workspaces_root=tmp_path,
    )

    result = build_workspace(store, settings, "ws1", tmp_path)
    assert result.workspace_id == "ws1"
    assert result.bindings_materialized == 0
    assert result.env_doc_files == []
