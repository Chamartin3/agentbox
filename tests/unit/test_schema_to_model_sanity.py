"""Sanity-gate tests for the JSON-Schema → pydantic converter.

These tests pin the structural fix that catches the class of authoring
bug where a schema declares a field in ``required`` but never declares
it in ``properties``. Before the fix the converter silently dropped
such fields, producing a result model that could never satisfy the
schema — opaque structured-output failures downstream on token-backend
runs (Claude CLI hid the bug because it never built a ``result_type``).
"""

from __future__ import annotations

import pytest
from agentbox.core.run.backends._schema_to_model import (
    InconsistentSchema,
    UnsupportedSchema,
    assert_schema_consistent,
    json_schema_to_pydantic_model,
)


def test_required_subset_of_properties_passes() -> None:
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
    }
    assert_schema_consistent(schema)
    model = json_schema_to_pydantic_model(schema, model_name="OK")
    inst = model(a="hi", b=1)
    assert inst.a == "hi"


def test_required_not_in_properties_raises() -> None:
    schema = {
        "type": "object",
        "required": ["a", "ghost"],
        "properties": {"a": {"type": "string"}},
    }
    with pytest.raises(InconsistentSchema) as exc:
        assert_schema_consistent(schema)
    assert "ghost" in str(exc.value)


def test_required_not_in_properties_raises_via_converter() -> None:
    schema = {
        "type": "object",
        "required": ["a", "ghost"],
        "properties": {"a": {"type": "string"}},
    }
    with pytest.raises(UnsupportedSchema):
        json_schema_to_pydantic_model(schema)


def test_inconsistent_schema_is_unsupported_subclass() -> None:
    # Existing callers catch UnsupportedSchema; the new precise error
    # must keep working with those handlers.
    assert issubclass(InconsistentSchema, UnsupportedSchema)


def test_nested_oneOf_branch_inconsistency_caught() -> None:
    # Reproduces the extract_keywords bug shape: the Success branch
    # lists role_summary/seniority_level/role_type in `required` but
    # never declares them as properties.
    schema = {
        "oneOf": [
            {
                "type": "object",
                "title": "Success",
                "required": [
                    "role_summary",
                    "seniority_level",
                    "role_type",
                    "keywords",
                ],
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"k": {"type": "string"}},
                        },
                        "minItems": 1,
                    },
                },
            },
            {
                "type": "object",
                "title": "Failure",
                "required": ["reason"],
                "properties": {"reason": {"enum": ["other"]}},
            },
        ]
    }
    with pytest.raises(InconsistentSchema) as exc:
        assert_schema_consistent(schema)
    msg = str(exc.value)
    assert "role_summary" in msg


def test_required_without_properties_raises() -> None:
    schema = {"type": "object", "required": ["a"]}
    with pytest.raises(InconsistentSchema):
        assert_schema_consistent(schema)


def test_root_oneOf_produces_union_root_model() -> None:
    # Previously a root-level oneOf fell through to build_object and
    # produced an empty model — silently dropping the union semantics.
    schema = {
        "oneOf": [
            {
                "type": "object",
                "title": "Success",
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            },
            {
                "type": "object",
                "title": "Failure",
                "required": ["reason"],
                "properties": {"reason": {"type": "string"}},
            },
        ]
    }
    model = json_schema_to_pydantic_model(schema, model_name="Result")
    # RootModel exposes `.root`; both branches must round-trip.
    a = model.model_validate({"ok": True})
    b = model.model_validate({"reason": "boom"})
    assert getattr(a, "root", a).ok is True
    assert getattr(b, "root", b).reason == "boom"


def test_ref_target_walked() -> None:
    schema = {
        "$defs": {
            "Bad": {
                "type": "object",
                "required": ["missing"],
                "properties": {"present": {"type": "string"}},
            }
        },
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/Bad"}},
    }
    with pytest.raises(InconsistentSchema) as exc:
        assert_schema_consistent(schema)
    assert "missing" in str(exc.value)


def test_array_items_walked() -> None:
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["k"],
                    "properties": {"j": {"type": "string"}},
                },
            }
        },
    }
    with pytest.raises(InconsistentSchema):
        assert_schema_consistent(schema)


def test_extract_keywords_actual_broken_schema_caught() -> None:
    # Verbatim shape of the failing run b851e03d... — the regression test
    # for the structural fix. If this passes assert_schema_consistent the
    # whole gate is broken.
    schema = {
        "oneOf": [
            {
                "type": "object",
                "title": "Success",
                "required": [
                    "role_summary",
                    "seniority_level",
                    "role_type",
                    "keywords",
                ],
                "properties": {
                    "keywords": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": [
                                "keyword",
                                "category",
                                "importance",
                                "frequency",
                            ],
                            "properties": {
                                "keyword": {"type": "string"},
                                "category": {"enum": ["a", "b"]},
                                "importance": {"type": "integer"},
                                "frequency": {"type": "integer"},
                            },
                        },
                    },
                    "reason": {"type": "null"},
                },
            },
            {
                "type": "object",
                "title": "Failure",
                "required": ["reason"],
                "properties": {
                    "reason": {"enum": ["empty_post_text", "other"]},
                },
            },
        ]
    }
    with pytest.raises(InconsistentSchema):
        assert_schema_consistent(schema)
