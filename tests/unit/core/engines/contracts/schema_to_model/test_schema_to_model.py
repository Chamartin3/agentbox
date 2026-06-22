"""Tests for ``_schema_to_model.json_schema_to_pydantic_model``.

These cover the constraints the token backend needs to keep enforced
once it stops appending the JSON schema in the system prompt: required
fields, enums, length/pattern, ``additionalProperties=false``,
descriptions and ranges.
"""

from __future__ import annotations

import pytest
from agentbox.core.engines.contracts.schema_to_model import (
    UnsupportedSchema,
    json_schema_to_pydantic_model,
)
from pydantic import ValidationError


def test_required_and_optional_fields() -> None:
    model = json_schema_to_pydantic_model(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "nickname": {"type": "string"},
            },
            "required": ["name"],
        }
    )
    model.model_validate({"name": "x"})
    with pytest.raises(ValidationError):
        model.model_validate({})


def test_enum_becomes_literal() -> None:
    model = json_schema_to_pydantic_model(
        {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["draft", "final"]}},
            "required": ["status"],
        }
    )
    model.model_validate({"status": "draft"})
    with pytest.raises(ValidationError):
        model.model_validate({"status": "approved"})


def test_string_constraints_enforced() -> None:
    model = json_schema_to_pydantic_model(
        {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "minLength": 3,
                    "maxLength": 4,
                    "pattern": "^[A-Z]+$",
                }
            },
            "required": ["code"],
        }
    )
    model.model_validate({"code": "ABCD"})
    with pytest.raises(ValidationError):
        model.model_validate({"code": "AB"})
    with pytest.raises(ValidationError):
        model.model_validate({"code": "abcd"})


def test_additional_properties_false() -> None:
    model = json_schema_to_pydantic_model(
        {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
            "required": ["a"],
            "additionalProperties": False,
        }
    )
    model.model_validate({"a": 1})
    with pytest.raises(ValidationError):
        model.model_validate({"a": 1, "extra": 2})


def test_numeric_ranges() -> None:
    model = json_schema_to_pydantic_model(
        {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["n"],
        }
    )
    model.model_validate({"n": 5})
    with pytest.raises(ValidationError):
        model.model_validate({"n": -1})
    with pytest.raises(ValidationError):
        model.model_validate({"n": 11})


def test_nested_object_and_array_items() -> None:
    model = json_schema_to_pydantic_model(
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                        "required": ["id"],
                    },
                }
            },
            "required": ["items"],
        }
    )
    model.model_validate({"items": [{"id": 1}, {"id": 2}]})
    with pytest.raises(ValidationError):
        model.model_validate({"items": [{"id": "nope"}]})


def test_ref_resolution() -> None:
    schema = {
        "type": "object",
        "properties": {"owner": {"$ref": "#/$defs/Person"}},
        "required": ["owner"],
        "$defs": {
            "Person": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        },
    }
    model = json_schema_to_pydantic_model(schema)
    model.model_validate({"owner": {"name": "x"}})
    with pytest.raises(ValidationError):
        model.model_validate({"owner": {}})


def test_unsupported_root_type_raises() -> None:
    with pytest.raises(UnsupportedSchema):
        json_schema_to_pydantic_model({"type": "string"})
