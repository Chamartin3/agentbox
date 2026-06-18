"""Tests for the token backend adapter — schema conversion and render (formerly pydantic_ai_structured)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


class TestJsonSchemaToPydanticModel:
    def _make_model(self):
        from agentbox.core.engines.backends.token import _json_schema_to_pydantic_model

        return _json_schema_to_pydantic_model

    def test_simple_object_schema(self) -> None:
        to_model = self._make_model()
        schema = {
            "type": "object",
            "required": ["name", "count"],
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
        }
        Model = to_model(schema)
        instance = Model(name="test", count=5)
        assert instance.name == "test"
        assert instance.count == 5

    def test_missing_required_raises(self) -> None:
        to_model = self._make_model()
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        Model = to_model(schema)
        with pytest.raises(ValueError):
            Model()

    def test_optional_field_defaults_to_none(self) -> None:
        to_model = self._make_model()
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "note": {"type": "string"},
            },
        }
        Model = to_model(schema)
        instance = Model(name="test")
        assert instance.name == "test"
        assert instance.note is None

    def test_array_of_strings(self) -> None:
        to_model = self._make_model()
        schema = {
            "type": "object",
            "required": ["tags"],
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
        }
        Model = to_model(schema)
        instance = Model(tags=["a", "b"])
        assert instance.tags == ["a", "b"]

    def test_nested_object_with_ref(self) -> None:
        to_model = self._make_model()
        schema = {
            "type": "object",
            "required": ["item"],
            "properties": {
                "item": {"$ref": "#/$defs/Item"},
            },
            "$defs": {
                "Item": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer"}},
                }
            },
        }
        Model = to_model(schema)
        nested = Model(item={"id": 42})
        assert nested.item.id == 42

    def test_array_of_refs(self) -> None:
        to_model = self._make_model()
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Item"},
                },
            },
            "$defs": {
                "Item": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer"}},
                }
            },
        }
        Model = to_model(schema)
        instance = Model(items=[{"id": 1}, {"id": 2}])
        assert len(instance.items) == 2
        assert instance.items[0].id == 1


class TestTokenBackendRender:
    def test_render_builds_agent_meta(self, tmp_path: Path) -> None:
        from agentbox.core.db import AgentDef, RunnerSpec
        from agentbox.core.engines.backends.token import TokenBackend

        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        (tmp_path / "output_schema.json").write_text(json.dumps(schema))

        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="token",
                output_schema_path="output_schema.json",
                timeout_seconds=60,
            ),
        )
        agent.__dict__["_config_json"] = {
            "python": {"output_schema_path": "output_schema.json"},
        }

        backend = TokenBackend()
        rendered = backend.render(
            agent,
            tmp_path,
            runner_config=SimpleNamespace(
                model="openai:gpt-4o",
            ),
        )

        assert rendered.agent_meta["model"] == "openai:gpt-4o"
        assert rendered.agent_meta["output_schema"] == schema
        assert rendered.agent_meta["timeout_seconds"] == 60

    def test_render_handles_missing_schema(self, tmp_path: Path) -> None:
        from agentbox.core.db import AgentDef, RunnerSpec
        from agentbox.core.engines.backends.token import TokenBackend

        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="token",
                output_schema_path="nonexistent.json",
            ),
        )

        backend = TokenBackend()
        rendered = backend.render(agent, tmp_path)

        assert rendered.agent_meta["output_schema"] is None
