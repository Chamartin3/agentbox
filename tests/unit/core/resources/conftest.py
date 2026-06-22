"""Shared builders for `core/resources` unit tests.

These factory fixtures replace the per-file `_blob` / `_make_binding`
dict-builders that were duplicated across ``test_materializer.py`` and
``test_binding_materialize.py``. Tests receive them via dependency
injection instead of constructing blob/binding dicts inline.
"""

from __future__ import annotations

import pytest


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
