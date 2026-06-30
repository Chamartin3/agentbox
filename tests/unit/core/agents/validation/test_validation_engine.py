"""Tests for output_validation_engine — config, selection, and hint text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentbox.core.agents.composition.bundle import _append_validation_engine_hint
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.agents.validation import validate_output


# ---------------------------------------------------------------------------
# Config tests (RunnerSpec.output_validation_engine)
# ---------------------------------------------------------------------------


class TestOutputValidationEngine:
    def test_default_is_both(self) -> None:
        spec = RunnerSpec()
        assert spec.output_validation_engine == "both"

    def test_accepts_jsonschema(self) -> None:
        spec = RunnerSpec(output_validation_engine="jsonschema")
        assert spec.output_validation_engine == "jsonschema"

    def test_accepts_pydantic(self) -> None:
        spec = RunnerSpec(output_validation_engine="pydantic")
        assert spec.output_validation_engine == "pydantic"

    def test_accepts_both(self) -> None:
        spec = RunnerSpec(output_validation_engine="both")
        assert spec.output_validation_engine == "both"

    def test_rejects_invalid_value(self) -> None:
        with pytest.raises(ValidationError):
            RunnerSpec(output_validation_engine="invalid")

    def test_roundtrips_with_other_fields(self) -> None:
        spec = RunnerSpec(
            timeout_seconds=300,
            output_schema_path="output_schema.json",
            output_validation_engine="pydantic",
            max_validation_retries=2,
        )
        assert spec.timeout_seconds == 300
        assert spec.output_schema_path == "output_schema.json"
        assert spec.output_validation_engine == "pydantic"
        assert spec.max_validation_retries == 2


# ---------------------------------------------------------------------------
# Engine selection tests
# ---------------------------------------------------------------------------


def _validate(output: str, agent: AgentDef, workdir: Path) -> tuple[bool, str, str]:
    """Compatibility shim around the new ValidationResult API."""
    # config_json is the only source of truth; mirror RunnerSpec fields into it.
    agent.__dict__["_config_json"] = {
        "execution": {
            "output_validation_engine": agent.runner.output_validation_engine,
        },
        "python": {"output_schema_path": agent.runner.output_schema_path},
    }
    r = validate_output(agent, workdir, output)
    return r.ok, r.error, r.engine


_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
}

_VALID = json.dumps({"name": "test"})
_INVALID = json.dumps({"name": 123})


class TestValidationEngineSelection:
    def test_jsonschema_only_passes_valid(self, tmp_path: Path) -> None:
        (tmp_path / "schema.json").write_text(json.dumps(_SCHEMA))
        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="claude_code",
                output_schema_path="schema.json",
                output_validation_engine="jsonschema",
            ),
        )
        ok, _err, via = _validate(_VALID, agent, tmp_path)
        assert ok
        assert via == "jsonschema"

    def test_jsonschema_only_rejects_invalid(self, tmp_path: Path) -> None:
        (tmp_path / "schema.json").write_text(json.dumps(_SCHEMA))
        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="claude_code",
                output_schema_path="schema.json",
                output_validation_engine="jsonschema",
            ),
        )
        ok, _err, via = _validate(_INVALID, agent, tmp_path)
        assert not ok
        assert via == "jsonschema"

    def test_pydantic_only_passes_valid(self, tmp_path: Path) -> None:
        (tmp_path / "schema.json").write_text(json.dumps(_SCHEMA))
        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="claude_code",
                output_schema_path="schema.json",
                output_validation_engine="pydantic",
            ),
        )
        ok, _err, via = _validate(_VALID, agent, tmp_path)
        assert ok
        assert via == "pydantic"

    def test_pydantic_only_rejects_invalid(self, tmp_path: Path) -> None:
        (tmp_path / "schema.json").write_text(json.dumps(_SCHEMA))
        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="claude_code",
                output_schema_path="schema.json",
                output_validation_engine="pydantic",
            ),
        )
        ok, _err, via = _validate(_INVALID, agent, tmp_path)
        assert not ok
        assert via == "pydantic"

    def test_both_passes_valid(self, tmp_path: Path) -> None:
        (tmp_path / "schema.json").write_text(json.dumps(_SCHEMA))
        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="claude_code",
                output_schema_path="schema.json",
                output_validation_engine="both",
            ),
        )
        ok, _err, via = _validate(_VALID, agent, tmp_path)
        assert ok
        assert via == "both"

    def test_both_fails_on_jsonschema_first(self, tmp_path: Path) -> None:
        """When both engines are enabled, jsonschema runs first."""
        (tmp_path / "schema.json").write_text(json.dumps(_SCHEMA))
        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="claude_code",
                output_schema_path="schema.json",
                output_validation_engine="both",
            ),
        )
        ok, _err, via = _validate(_INVALID, agent, tmp_path)
        assert not ok
        assert via == "jsonschema"

    def test_default_engine_is_both(self, tmp_path: Path) -> None:
        """When output_validation_engine is not set, default to both."""
        (tmp_path / "schema.json").write_text(json.dumps(_SCHEMA))
        agent = AgentDef(
            id="test",
            description="t",
            runner=RunnerSpec(
                kind="claude_code",
                output_schema_path="schema.json",
            ),
        )
        ok, _err, via = _validate(_VALID, agent, tmp_path)
        assert ok
        assert via == "both"


# ---------------------------------------------------------------------------
# Validation engine hint appended to system prompt
# ---------------------------------------------------------------------------


class TestAppendValidationEngineHint:
    def test_both_engine_hint(self) -> None:
        result = _append_validation_engine_hint("## Role\n\nYou are a helper.", "both")
        assert "validated twice" in result
        assert "JSON Schema" in result
        assert "pydantic" in result

    def test_jsonschema_engine_hint(self) -> None:
        result = _append_validation_engine_hint(
            "## Role\n\nYou are a helper.", "jsonschema"
        )
        assert "JSON Schema" in result
        assert "validated twice" not in result

    def test_pydantic_engine_hint(self) -> None:
        result = _append_validation_engine_hint(
            "## Role\n\nYou are a helper.", "pydantic"
        )
        assert "pydantic" in result
        assert "validated twice" not in result

    def test_empty_text(self) -> None:
        result = _append_validation_engine_hint("", "both")
        assert "## Validation" in result

    def test_unknown_engine_defaults_to_both(self) -> None:
        result = _append_validation_engine_hint(
            "## Role\n\nYou are a helper.", "unknown"
        )
        assert "validated twice" in result
