"""Unit tests for shared resource references in composition.

Tests the SharedRef model, shared ref detection, and content resolution.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.core.composition import (
    _fetch_shared_content,
    _is_shared_ref,
    _resolve_shared_ref,
)
from agentbox.core.data.manifest import SharedRef
from agentbox.core.data.records import SharedResourceRecord


class TestSharedRefModel:
    """Test SharedRef Pydantic model."""

    def test_shared_ref_minimal(self) -> None:
        ref = SharedRef(shared="my-resource")
        assert ref.shared == "my-resource"
        assert ref.version is None

    def test_shared_ref_with_version(self) -> None:
        ref = SharedRef(shared="my-resource", version=2)
        assert ref.shared == "my-resource"
        assert ref.version == 2

    def test_shared_ref_forbids_extra_fields(self) -> None:
        with pytest.raises(Exception):  # Pydantic ValidationError
            SharedRef(shared="x", extra_field="not_allowed")  # type: ignore


class TestSharedRefDetection:
    """Test _is_shared_ref() detection logic."""

    def test_is_shared_ref_with_dict(self) -> None:
        assert _is_shared_ref({"shared": "x"})
        assert _is_shared_ref({"shared": "x", "version": 1})
        assert not _is_shared_ref({"shared": 123})
        assert not _is_shared_ref({"path": "x"})

    def test_is_shared_ref_with_object(self) -> None:
        ref = SharedRef(shared="x")
        assert _is_shared_ref(ref)

    def test_is_shared_ref_with_string(self) -> None:
        assert not _is_shared_ref("not a ref")

    def test_is_shared_ref_with_none(self) -> None:
        assert not _is_shared_ref(None)


class TestSharedRefResolution:
    """Test _resolve_shared_ref() extraction."""

    def test_resolve_dict_minimal(self) -> None:
        shared_id, version = _resolve_shared_ref({"shared": "my-id"}, None)
        assert shared_id == "my-id"
        assert version is None

    def test_resolve_dict_with_version(self) -> None:
        shared_id, version = _resolve_shared_ref(
            {"shared": "my-id", "version": 3}, None
        )
        assert shared_id == "my-id"
        assert version == 3

    def test_resolve_object(self) -> None:
        ref = SharedRef(shared="my-id", version=2)
        shared_id, version = _resolve_shared_ref(ref, None)
        assert shared_id == "my-id"
        assert version == 2

    def test_resolve_invalid_dict(self) -> None:
        with pytest.raises(ValueError):
            _resolve_shared_ref({"shared": 123}, None)

        with pytest.raises(ValueError):
            _resolve_shared_ref({"no_shared": "x"}, None)


class TestSharedContentFetch:
    """Test _fetch_shared_content() store interaction."""

    def test_fetch_text_active_version(self) -> None:
        mock_store = MagicMock()
        record = SharedResourceRecord(
            id="my-res",
            version=1,
            kind="guideline",
            name="My Resource",
            content="Hello World",
            config_json=None,
            sha256="abc123",
            is_active=True,
            author="test",
            changelog="",
            tags=(),
            created_at="2025-01-01T00:00:00Z",
        )
        mock_store.get_active_resource.return_value = record

        result = _fetch_shared_content("my-res", None, mock_store, "text")
        assert result == "Hello World"
        mock_store.get_active_resource.assert_called_once_with("my-res")

    def test_fetch_text_specific_version(self) -> None:
        mock_store = MagicMock()
        record = SharedResourceRecord(
            id="my-res",
            version=2,
            kind="guideline",
            name="My Resource",
            content="Version 2 Content",
            config_json=None,
            sha256="def456",
            is_active=False,
            author="test",
            changelog="updated",
            tags=(),
            created_at="2025-01-02T00:00:00Z",
        )
        mock_store.get_resource.return_value = record

        result = _fetch_shared_content("my-res", 2, mock_store, "text")
        assert result == "Version 2 Content"
        mock_store.get_resource.assert_called_once_with("my-res", 2)

    def test_fetch_json_schema(self) -> None:
        mock_store = MagicMock()
        schema_obj = {"type": "object", "properties": {"name": {"type": "string"}}}
        record = SharedResourceRecord(
            id="schema/eval",
            version=1,
            kind="schema",
            name="Eval Schema",
            content=None,
            config_json=json.dumps(schema_obj),
            sha256="ghi789",
            is_active=True,
            author="test",
            changelog="",
            tags=(),
            created_at="2025-01-01T00:00:00Z",
        )
        mock_store.get_active_resource.return_value = record

        result = _fetch_shared_content("schema/eval", None, mock_store, "json")
        assert result == schema_obj

    def test_fetch_missing_active(self) -> None:
        mock_store = MagicMock()
        mock_store.get_active_resource.return_value = None

        with pytest.raises(ValueError, match="not found"):
            _fetch_shared_content("missing-res", None, mock_store, "text")

    def test_fetch_missing_version(self) -> None:
        mock_store = MagicMock()
        mock_store.get_resource.return_value = None

        with pytest.raises(ValueError, match="version 3 not found"):
            _fetch_shared_content("my-res", 3, mock_store, "text")

    def test_fetch_empty_content_raises(self) -> None:
        mock_store = MagicMock()
        record = SharedResourceRecord(
            id="empty-res",
            version=1,
            kind="test",
            name="Empty",
            content=None,
            config_json=None,
            sha256="",
            is_active=True,
            author="test",
            changelog="",
            tags=(),
            created_at="2025-01-01T00:00:00Z",
        )
        mock_store.get_active_resource.return_value = record

        with pytest.raises(ValueError, match="has no content"):
            _fetch_shared_content("empty-res", None, mock_store, "text")
