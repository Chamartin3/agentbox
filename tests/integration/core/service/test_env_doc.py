"""Tests for the env-doc service free functions — preview, save+sync.

The env-doc is plain markdown text stored as ``content_json = {"body": ...}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from agentbox.core.db.database import Database
from agentbox.core.service.workspaces import (
    WorkspaceService,
    env_doc_body,
    render_env_doc_preview,
)


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


@pytest.fixture
def settings() -> object:
    """Fake settings with minimal attributes for build_workspace_by_name."""

    @dataclass
    class _S:
        project_root: Path = Path("/tmp")

    return _S()


# ── env_doc_body ────────────────────────────────────────────────────────


def test_env_doc_body_from_string_and_dict() -> None:
    assert env_doc_body("# Hi") == "# Hi"
    assert env_doc_body({"body": "# Hi"}) == "# Hi"
    assert env_doc_body({}) == ""
    assert env_doc_body(None) == ""


# ── render_env_doc_preview ──────────────────────────────────────────────


def test_render_env_doc_preview_identical_body() -> None:
    result = render_env_doc_preview("# Test Workspace\n\nIntegration testing")
    assert result["claude_md"] == result["agents_md"]
    assert "Test Workspace" in result["claude_md"]


# ── save_and_sync_env_doc ───────────────────────────────────────────────


def test_save_and_sync_env_doc_creates_version(
    store: Database, settings: object
) -> None:
    store.workspaces.insert("test-ws")
    result = WorkspaceService().save_and_sync_env_doc("test-ws", content="# Test\n\nTesting")
    assert isinstance(result, dict)
    assert result.get("changelog") is not None
    active = store.workspace_env_doc_versions.get_active("test-ws")
    assert active is not None
    assert active["content_json"]["body"] == "# Test\n\nTesting"


def test_save_and_sync_missing_workspace(
    store: Database, settings: object
) -> None:
    """save_env_doc creates a workspace record if none exists, so this
    verifies the function completes rather than crashing."""
    result = WorkspaceService().save_and_sync_env_doc("nonexistent", content="# X")
    assert isinstance(result, dict)
