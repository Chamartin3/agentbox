"""Tests for SchemaImporter."""

from __future__ import annotations

import json

import pytest
from agentbox.core.resources.importers.base import ImporterContext
from agentbox.core.resources.importers.schema import SchemaImporter


def _run(payload: bytes, filename: str = "s.json"):
    return SchemaImporter(filename=filename, content=payload).run(ImporterContext())


def test_valid_schema_marks_is_valid_true():
    doc = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Person",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    result = _run(json.dumps(doc).encode())
    assert result.suggested_type == "schema"
    assert result.suggested_display_name == "Person"
    assert result.metadata is not None
    assert result.metadata["is_valid"] is True
    assert result.metadata["validation_errors"] == []
    assert result.metadata["schema_dialect"] == doc["$schema"]
    assert len(result.blobs) == 1
    assert result.blobs[0][2] == "application/schema+json"


def test_invalid_schema_marks_is_valid_false():
    doc = {"type": "not-a-real-type"}
    result = _run(json.dumps(doc).encode())
    assert result.metadata is not None
    assert result.metadata["is_valid"] is False
    assert result.metadata["validation_errors"]


def test_non_json_payload_raises():
    with pytest.raises(ValueError, match="not valid JSON"):
        _run(b"{not-json")


def test_non_object_payload_raises():
    with pytest.raises(ValueError, match="must be a JSON object"):
        _run(b"[1, 2, 3]")


def test_default_dialect_when_missing():
    result = _run(b'{"type": "object"}')
    assert result.metadata is not None
    assert "draft/2020-12" in result.metadata["schema_dialect"]
