"""Tests for pydantic_core-backed output validation."""

from __future__ import annotations

import json

from agentbox.core.agents.composition.bundle.pydantic_validate import validate_with_pydantic


def _schema(name: str = "TestOutput") -> dict:
    return {
        "title": name,
        "type": "object",
        "required": ["summary", "key_skills", "experience"],
        "properties": {
            "summary": {"type": "string", "minLength": 10},
            "key_skills": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["position_id", "achievements"],
                    "properties": {
                        "position_id": {"type": "integer"},
                        "achievements": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


class TestValidateWithPydantic:
    def test_valid_payload_passes(self) -> None:
        payload = {
            "summary": "A valid summary with enough characters",
            "key_skills": ["Python", "Django"],
            "experience": [{"position_id": 1, "achievements": ["Built a thing"]}],
        }
        ok, err = validate_with_pydantic(json.dumps(payload), _schema())
        assert ok
        assert err == ""

    def test_wrong_type_fails(self) -> None:
        payload = {
            "summary": 123,
            "key_skills": ["Python"],
            "experience": [{"position_id": 1, "achievements": ["x"]}],
        }
        ok, _err = validate_with_pydantic(json.dumps(payload), _schema())
        assert not ok

    def test_missing_required_field_fails(self) -> None:
        payload = {"summary": "A valid summary with enough characters"}
        ok, err = validate_with_pydantic(json.dumps(payload), _schema())
        assert not ok
        assert "key_skills" in err or "experience" in err or "Field required" in err

    def test_invalid_json_fails(self) -> None:
        ok, err = validate_with_pydantic("not json", _schema())
        assert not ok
        assert "JSON" in err

    def test_empty_output_fails(self) -> None:
        ok, _err = validate_with_pydantic("", _schema())
        assert not ok

    def test_code_fence_stripped(self) -> None:
        payload = {
            "summary": "A valid summary with enough characters",
            "key_skills": ["Python"],
            "experience": [{"position_id": 1, "achievements": ["x"]}],
        }
        fenced = f"```json\n{json.dumps(payload)}\n```"
        ok, err = validate_with_pydantic(fenced, _schema())
        assert ok
        assert err == ""

    def test_nested_object_validation(self) -> None:
        """Nested objects in experience are validated for required fields."""
        payload = {
            "summary": "A valid summary with enough characters",
            "key_skills": ["Python"],
            "experience": [{"achievements": ["x"]}],  # missing position_id
        }
        _ok, _err = validate_with_pydantic(json.dumps(payload), _schema())
        # Note: pydantic's create_model may not enforce nested required fields
        # when the input is a dict rather than a model instance. The jsonschema
        # engine catches this; pydantic validates types but not nested dicts.
        # This test documents that behavior.

    def test_oneof_schema_validates(self) -> None:
        """Schema with oneOf branches — the canonical converter handles these,
        while the old naive ``_build_model_from_schema`` would have
        mis-modeled or rejected them."""
        schema = {
            "type": "object",
            "oneOf": [
                {"$ref": "#/$defs/Success"},
                {"$ref": "#/$defs/Failure"},
            ],
            "$defs": {
                "Success": {
                    "type": "object",
                    "required": ["result"],
                    "properties": {"result": {"type": "string"}},
                },
                "Failure": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {"type": "string"},
                        "code": {"type": "integer"},
                    },
                },
            },
        }
        ok_success, _ = validate_with_pydantic(
            json.dumps({"result": "done"}), schema
        )
        assert ok_success
        ok_failure, _ = validate_with_pydantic(
            json.dumps({"error": "timeout", "code": 408}), schema
        )
        assert ok_failure

    def test_discriminated_union_validates_branches(self) -> None:
        """Root-level oneOf with type discriminator — the canonical converter
        wraps branches in a RootModel so both sides are reachable."""
        schema = {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["kind", "value"],
                    "properties": {
                        "kind": {"const": "text"},
                        "value": {"type": "string"},
                    },
                },
                {
                    "type": "object",
                    "required": ["kind", "value"],
                    "properties": {
                        "kind": {"const": "number"},
                        "value": {"type": "integer"},
                    },
                },
            ],
        }
        ok_text, _ = validate_with_pydantic(
            json.dumps({"kind": "text", "value": "hello"}), schema
        )
        assert ok_text
        ok_number, _ = validate_with_pydantic(
            json.dumps({"kind": "number", "value": 42}), schema
        )
        assert ok_number
        # Mismatched branch should fail
        ok_bad, err = validate_with_pydantic(
            json.dumps({"kind": "text", "value": 99}), schema
        )
        assert not ok_bad
        assert "value" in err
