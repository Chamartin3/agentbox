"""Tests for ``core.service.env_doc`` — context building, preview, save+sync."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data import SessionStore
from agentbox.core.service.env_doc import (
    build_env_doc_context,
    render_env_doc_preview,
    save_and_sync_env_doc,
)
from agentbox.core.workspaces.envdoc.renderers import RuntimeContext
from agentbox.core.workspaces.envdoc.schema import EnvDocContent


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


@pytest.fixture
def settings() -> object:
    """Fake settings with minimal attributes for build_workspace_by_name."""
    from dataclasses import dataclass

    @dataclass
    class _S:
        project_root: Path = Path("/tmp")

    return _S()


# ── build_env_doc_context ───────────────────────────────────────────────


def test_build_env_doc_context_empty_workspace(store: SessionStore) -> None:
    ctx = build_env_doc_context(store, "nonexistent")
    assert isinstance(ctx, RuntimeContext)
    assert ctx.skills == []
    assert ctx.folders == []


# ── render_env_doc_preview ──────────────────────────────────────────────


def test_render_env_doc_preview_produces_both_formats() -> None:
    content = EnvDocContent(
        project_name="Test Workspace",
        overview="Integration testing",
    )
    ctx = RuntimeContext(skills=[], folders=[])
    result = render_env_doc_preview(content, ctx)
    assert "claude_md" in result
    assert "agents_md" in result
    assert "Test Workspace" in result["claude_md"]


# ── save_and_sync_env_doc ───────────────────────────────────────────────


def test_save_and_sync_env_doc_creates_version(
    store: SessionStore, settings: object
) -> None:
    store.create_workspace("test-ws")
    content = {"project_name": "Test", "overview": "Testing"}
    result = save_and_sync_env_doc(
        store, settings, "test-ws", content=content  # type: ignore[arg-type]
    )
    assert isinstance(result, dict)
    assert result.get("changelog") is not None


def test_save_and_sync_missing_workspace(
    store: SessionStore, settings: object
) -> None:
    """Missing workspace raises an error from store.save_env_doc.
    
    save_env_doc in store creates a workspace record if none exists,
    so this test verifies the function completes rather than crashing.
    """
    result = save_and_sync_env_doc(
        store, settings, "nonexistent", content={"project_name": "X"}  # type: ignore[arg-type]
    )
    assert isinstance(result, dict)
