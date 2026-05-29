"""Tests for schema_to_pydantic."""

from __future__ import annotations

import json

from agentbox.core.resource.pydantic_export import schema_to_pydantic


def test_simple_schema_renders_pydantic_class():
    schema = {
        "title": "Person",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name"],
    }
    code = schema_to_pydantic(json.dumps(schema), class_name="Person")
    assert "class Person" in code
    assert "BaseModel" in code
    assert "name:" in code
    assert "age:" in code
