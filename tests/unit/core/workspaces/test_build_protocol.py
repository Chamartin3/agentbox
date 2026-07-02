"""Plan 08 — verify build_workspace accepts manager interfaces."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from agentbox.core.workspaces.build import build_workspace


def test_build_workspace_accepts_narrow_protocol(tmp_path):
    # Create mocks for each manager parameter
    workspaces = MagicMock()
    workspaces.get_by_name.return_value = {"id": "ws1", "path": str(tmp_path)}

    agent_defs = MagicMock()
    workspace_subagents = MagicMock()
    workspace_subagents.list_for_workspace.return_value = []

    agent_versions = MagicMock()
    workspace_file_resource_bindings = MagicMock()
    workspace_file_resource_bindings.list_for_workspace.return_value = []

    resources = MagicMock()
    resource_versions = MagicMock()
    resource_blobs = MagicMock()

    workspace_mcp_overrides = MagicMock()
    workspace_mcp_tool_overrides = MagicMock()

    workspace_env_doc_versions = MagicMock()
    workspace_env_doc_versions.get_active.return_value = None

    settings = SimpleNamespace(
        resource_cache_dir=tmp_path / "cache",
        project_root=tmp_path,
        workspaces_root=tmp_path,
    )

    result = build_workspace(
        workspaces,
        agent_defs,
        workspace_subagents,
        agent_versions,
        workspace_file_resource_bindings,
        resources,
        resource_versions,
        resource_blobs,
        workspace_mcp_overrides,
        workspace_mcp_tool_overrides,
        workspace_env_doc_versions,
        settings,
        "ws1",
        tmp_path,
    )
    assert result.workspace_id == "ws1"
    assert result.bindings_materialized == 0
    assert result.env_doc_files == []
