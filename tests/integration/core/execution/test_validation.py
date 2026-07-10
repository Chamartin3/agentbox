"""Tests for the Agents output validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from agentbox.core.agents.validation import (
    ValidationResult,
    check_output,
    validate_jsonschema,
    validate_pydantic,
)
from agentbox.core.data._util import extract_json


# Minimal fake agent — only the attributes check_output() reads.
class _FakeAgent:
    def __init__(
        self,
        output_schema_path: str | None = None,
        engine: str = "jsonschema",
    ) -> None:
        self.composition = None
        # config_json is the sole source of truth — mirror runner fields here.
        self.__dict__["_config_json"] = {
            "execution": {"output_validation_engine": engine},
            "python": {"output_schema_path": output_schema_path},
        }


_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}


def test_extract_json_handles_fenced_block() -> None:
    """Models wrap JSON in ``` fences; validator must see through them."""
    fenced = '```json\n{"name": "x"}\n```'
    assert extract_json(fenced) == '{"name": "x"}'


def test_extract_json_handles_prose_around_object() -> None:
    """Falls back to the first {...} when no fence is present."""
    prose = 'Here is the answer:\n{"name": "x"}\nLet me know!'
    assert json.loads(extract_json(prose)) == {"name": "x"}


def test_validate_jsonschema_passes() -> None:
    result = validate_jsonschema('{"name": "x"}', _SCHEMA)
    assert result == ValidationResult(ok=True, engine="jsonschema")


def test_validate_jsonschema_reports_path() -> None:
    """Error message must include where it failed — agents need to fix
    the right place."""
    result = validate_jsonschema("{}", _SCHEMA)
    assert not result.ok
    assert result.engine == "jsonschema"
    assert "name" in result.error  # required field surfaced


def test_validate_jsonschema_handles_bad_json() -> None:
    result = validate_jsonschema("not json", _SCHEMA)
    assert not result.ok
    assert "not valid JSON" in result.error


def test_validate_output_off_when_no_schema(tmp_path: Path) -> None:
    """No composed schema, no path → no validation, ok=True."""
    agent = _FakeAgent(output_schema_path=None)
    result = check_output(agent, tmp_path, '{"anything": 1}')
    assert result == ValidationResult(ok=True, engine="off")


def test_validate_output_empty_when_schema_required(tmp_path: Path) -> None:
    """A schema is configured but output is empty → reportable failure."""
    agent = _FakeAgent()
    composed = SimpleNamespace(schema=_SCHEMA)
    result = check_output(agent, tmp_path, "", composed=composed)
    assert not result.ok
    assert result.engine == "none"
    assert "empty" in result.error


def test_validate_output_uses_composed_schema(tmp_path: Path) -> None:
    """Composed schema beats reading from disk — works for DB-only agents."""
    agent = _FakeAgent(engine="jsonschema")
    composed = SimpleNamespace(schema=_SCHEMA)
    result = check_output(agent, tmp_path, '{"name": "x"}', composed=composed)
    assert result.ok
    assert result.engine == "jsonschema"


def test_validate_output_falls_back_to_disk_schema(tmp_path: Path) -> None:
    """When composed schema isn't set, load from runner.output_schema_path."""
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(_SCHEMA))
    agent = _FakeAgent(output_schema_path="schema.json", engine="jsonschema")
    result = check_output(agent, tmp_path, '{"name": "x"}')
    assert result.ok


def test_validate_output_missing_schema_file(tmp_path: Path) -> None:
    agent = _FakeAgent(output_schema_path="nope.json")
    result = check_output(agent, tmp_path, '{"name": "x"}')
    assert not result.ok
    assert result.engine == "none"
    assert "not found" in result.error


def test_validate_output_both_engines(tmp_path: Path) -> None:
    """``both`` runs jsonschema first then pydantic — failure attribution
    matters for the retry prompt."""
    agent = _FakeAgent(engine="both")
    composed = SimpleNamespace(schema=_SCHEMA)
    result = check_output(agent, tmp_path, '{"name": "x"}', composed=composed)
    assert result.ok
    assert result.engine == "both"


def test_validate_pydantic_smoke() -> None:
    """Pydantic validation runs via the shared helper. Single smoke test —
    deep coverage lives in ``test_pydantic_validate``."""
    result = validate_pydantic('{"name": "x"}', _SCHEMA)
    assert result.engine == "pydantic"
