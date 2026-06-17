"""Tests for ``core.service.env_doc`` — preview, save+sync.

The env-doc is plain markdown text stored as ``content_json = {"body": ...}``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data import SessionStore
from agentbox.core.service.env_doc import (
    env_doc_body,
    render_env_doc_preview,
    save_and_sync_env_doc,
)


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
    store: SessionStore, settings: object
) -> None:
    store.create_workspace("test-ws")
    result = save_and_sync_env_doc(
        store, settings, "test-ws", content="# Test\n\nTesting"  # type: ignore[arg-type]
    )
    assert isinstance(result, dict)
    assert result.get("changelog") is not None
    active = store.get_active_env_doc("test-ws")
    assert active is not None
    assert active["content_json"]["body"] == "# Test\n\nTesting"


def test_save_and_sync_missing_workspace(
    store: SessionStore, settings: object
) -> None:
    """save_env_doc creates a workspace record if none exists, so this
    verifies the function completes rather than crashing."""
    result = save_and_sync_env_doc(
        store, settings, "nonexistent", content="# X"  # type: ignore[arg-type]
    )
    assert isinstance(result, dict)
