"""Tests for validation engine selection.

The engine selection logic lives in ``core/validation.validate_output``
(extracted from the executor in the streaming-session refactor). These
tests pin down the engine-dispatch rules; deep coverage of each engine
lives in ``test_validation.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentbox.core.data.manifest import AgentDef, RunnerSpec
from agentbox.core.run.validation import validate_output


def _validate(output: str, agent: AgentDef, workdir: Path) -> tuple[bool, str, str]:
    """Compatibility shim around the new ValidationResult API.

    Keeps the original ``(ok, err, via)`` tuple shape used throughout
    this file so the assertions don't need rewriting.
    """
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
        ok, err, via = _validate(_VALID, agent, tmp_path)
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
        ok, err, via = _validate(_INVALID, agent, tmp_path)
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
        ok, err, via = _validate(_VALID, agent, tmp_path)
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
        ok, err, via = _validate(_INVALID, agent, tmp_path)
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
        ok, err, via = _validate(_VALID, agent, tmp_path)
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
        ok, err, via = _validate(_INVALID, agent, tmp_path)
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
        ok, err, via = _validate(_VALID, agent, tmp_path)
        assert ok
        assert via == "both"
