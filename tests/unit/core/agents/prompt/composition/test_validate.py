"""Tests for output schema validation in the executor.

Covers:
- jsonschema is a hard dependency (not optional)
- _validate_output uses jsonschema.validate, not the old basic shape check
- Draft202012Validator.check_schema accepts well-formed oneOf schemas
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_jsonschema_importable() -> None:
    """jsonschema must be importable — it is a hard dep, not optional."""
    import jsonschema

    assert hasattr(jsonschema, "validate")
    assert hasattr(jsonschema, "ValidationError")


def test_no_basic_shape_check_fallback() -> None:
    """The executor must not have a _basic_shape_check fallback method."""
    from agentbox.core.execution.orchestrate.executor import RunExecutor

    assert not hasattr(RunExecutor, "_basic_shape_check"), (
        "_basic_shape_check was deleted in plan-011 — if it's back, "
        "someone reintroduced the silent-fallback path"
    )


class _ValidatorShim:
    """Compatibility wrapper so tests can keep calling
    ``executor._validate_output(output, agent, workdir) -> (ok, err, via)``.

    The real method moved to ``core.validation.validate_output`` (returns
    a ``ValidationResult``). Rather than rewrite every assertion, this
    shim adapts the new shape to the old tuple.
    """

    def _validate_output(
        self, output: str, agent, workdir: Path
    ) -> tuple[bool, str, str]:
        from agentbox.core.agents.validation import validate_output

        agent.__dict__["_config_json"] = {
            "execution": {
                "output_validation_engine": agent.runner.output_validation_engine,
            },
            "python": {"output_schema_path": agent.runner.output_schema_path},
        }
        r = validate_output(agent, workdir, output)
        return r.ok, r.error, r.engine


def _make_executor(tmp_path: Path):  # type: ignore[no-untyped-def]
    # Validation no longer needs an executor — return the shim to keep
    # the existing call sites working. The Settings/store/loader setup
    # was only ever used by ``_validate_output``, which now reads
    # everything it needs from the agent itself.
    return _ValidatorShim()


def test_validate_output_rejects_missing_required(tmp_path: Path) -> None:
    """_validate_output catches missing required field via jsonschema."""
    from agentbox.core.data import AgentDef, RunnerSpec

    schema = {
        "type": "object",
        "required": ["name", "value"],
        "properties": {
            "name": {"type": "string"},
            "value": {"type": "integer", "minimum": 1},
        },
    }
    (tmp_path / "schema.json").write_text(json.dumps(schema))
    agent = AgentDef(
        id="test",
        description="t",
        runner=RunnerSpec(kind="claude_code", output_schema_path="schema.json"),
    )
    executor = _make_executor(tmp_path)

    ok, err, _via = executor._validate_output(
        json.dumps({"name": "test"}),
        agent,
        tmp_path,  # missing "value"
    )
    assert not ok
    assert "value" in err

    ok, err, _via = executor._validate_output(
        json.dumps({"name": "test", "value": 5}), agent, tmp_path
    )
    assert ok
    assert err == ""


def test_validate_output_rejects_enum_violation(tmp_path: Path) -> None:
    """_validate_output rejects invalid enum values."""
    from agentbox.core.data import AgentDef, RunnerSpec

    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {
            "status": {"type": "string", "enum": ["ok", "fail"]},
        },
    }
    (tmp_path / "schema.json").write_text(json.dumps(schema))
    agent = AgentDef(
        id="test",
        description="t",
        runner=RunnerSpec(kind="claude_code", output_schema_path="schema.json"),
    )
    executor = _make_executor(tmp_path)

    ok, _err, _via = executor._validate_output(
        json.dumps({"status": "unknown"}), agent, tmp_path
    )
    assert not ok

    ok, _err, _via = executor._validate_output(
        json.dumps({"status": "ok"}), agent, tmp_path
    )
    assert ok


def test_oneof_schemas_are_valid_meta_schemas() -> None:
    """The oneOf discriminated-union pattern used in cvman specs is valid JSON Schema."""
    import jsonschema

    oneof_schema = {
        "oneOf": [
            {
                "title": "Success",
                "type": "object",
                "required": ["role_summary", "keywords"],
                "properties": {
                    "keywords": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "object"},
                    },
                    "reason": {"type": "null"},
                },
            },
            {
                "title": "Failure",
                "type": "object",
                "required": ["reason"],
                "properties": {
                    "reason": {"enum": ["empty_post_text", "other"]},
                },
            },
        ]
    }
    jsonschema.Draft202012Validator.check_schema(oneof_schema)

    # Valid success payload
    jsonschema.validate(
        instance={"role_summary": "foo", "keywords": [{"k": "v"}]},
        schema=oneof_schema,
    )

    # Failure payload
    jsonschema.validate(
        instance={"reason": "other"},
        schema=oneof_schema,
    )

    # Missing required field fails
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"role_summary": "foo"}, schema=oneof_schema)


def test_empty_output_treated_as_validation_failure(tmp_path: Path) -> None:
    """When output is empty/None but a schema is required, validation fails.

    Regression: the executor used to skip validation entirely when output
    was falsy (``if agent.runner.output_schema_path and output``), letting
    empty responses through to the post-processor which then crashed.
    """
    from agentbox.core.data import AgentDef, RunnerSpec

    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    (tmp_path / "schema.json").write_text(json.dumps(schema))
    agent = AgentDef(
        id="test",
        description="t",
        runner=RunnerSpec(kind="claude_code", output_schema_path="schema.json"),
    )
    executor = _make_executor(tmp_path)

    # Empty string → validation failure
    ok, _err, _via = executor._validate_output("", agent, tmp_path)
    assert not ok

    # Whitespace-only → validation failure
    ok, _err, _via = executor._validate_output("   \n", agent, tmp_path)
    assert not ok
