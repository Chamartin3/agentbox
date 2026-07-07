"""Shared fixtures for the workspace-generation render tests.

The Claude and OpenCode render suites previously each carried an
identical ``_make_fixture_config`` builder. It lives here now as a single
factory fixture so both suites share one source of truth.
"""

from __future__ import annotations

import pytest

from agentbox.core.data.workenv import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkenvConfig,
)


@pytest.fixture
def make_workenv_config():
    """Factory returning a fully-populated ``WorkenvConfig``.

    Pass keyword overrides to swap any field (e.g.
    ``make_workenv_config(mcp_servers=[])``).
    """

    def _make(**overrides: object) -> WorkenvConfig:
        kwargs: dict = {
            "name": "test-workspace",
            "description": "A test workspace",
            "env_doc": "# Hello\nThis is the env doc.",
            "agents": [
                AgentRef(id="main-agent", role="main"),
                AgentRef(id="sub-1", role="subagent"),
                AgentRef(id="sub-2", role="subagent"),
            ],
            "resources": [ResourceRef(id="res-1")],
            "skills": [ResourceRef(id="skill-1"), ResourceRef(id="skill-2")],
            "mcp_servers": [
                McpRef(
                    name="my-mcp",
                    config={"url": "http://localhost:8080", "transport": "http"},
                ),
            ],
            "permissions": Permissions(
                data={"allow": ["Read", "Write"], "deny": ["Bash"]}
            ),
            "env": {"KEY": "VAL"},
        }
        kwargs.update(overrides)
        return WorkenvConfig(**kwargs)

    return _make


# ── blob / binding builders (materialize + blobs suites) ─────────────────


@pytest.fixture
def make_blob():
    """Factory for a single materializer blob dict.

    ``relative_path=""`` is document mode (target_root is the file);
    a non-empty relative_path names a file within a folder target.
    """

    def _make(relative_path: str = "", content: bytes = b"data") -> dict:
        return {"relative_path": relative_path, "content": content}

    return _make


@pytest.fixture
def single_doc_blob(make_blob):
    """Factory returning a one-element document-mode blob list."""

    def _make(content: bytes = b"hello") -> list[dict]:
        return [make_blob(content=content)]

    return _make


@pytest.fixture
def folder_blobs(make_blob):
    """Factory returning folder/skill-mode blobs (non-empty relative_paths)."""

    def _make(*rel_paths: str, content: bytes = b"data") -> list[dict]:
        return [make_blob(p, content) for p in rel_paths]

    return _make


@pytest.fixture
def make_binding(make_blob):
    """Factory for a fully-resolved binding dict (for materialize_workspace)."""

    def _make(
        *,
        binding_id: str = "b1",
        resource_id: str = "r1",
        version_id: str = "v1",
        content_hash: str = "abc123",
        display_name: str = "notes",
        resource_type: str = "document",
        target_path: str | None = None,
        on_conflict: str = "error",
        materialize_mode: str = "copy",
        content: bytes = b"hello",
        source_metadata: dict | None = None,
    ) -> dict:
        return {
            "binding_id": binding_id,
            "resource_id": resource_id,
            "version_id": version_id,
            "content_hash": content_hash,
            "type": resource_type,
            "display_name": display_name,
            "target_path": target_path,
            "on_conflict": on_conflict,
            "materialize_mode": materialize_mode,
            "blobs": [make_blob(content=content)],
            "source_metadata": source_metadata,
        }

    return _make
