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
    import jsonschema  # noqa: F401

    assert hasattr(jsonschema, "validate")
    assert hasattr(jsonschema, "ValidationError")


def test_no_basic_shape_check_fallback() -> None:
    """The executor must not have a _basic_shape_check fallback method."""
    from agentbox.core.executor import RunExecutor

    assert not hasattr(RunExecutor, "_basic_shape_check"), (
        "_basic_shape_check was deleted in plan-011 — if it's back, "
        "someone reintroduced the silent-fallback path"
    )


def _make_executor(tmp_path: Path):  # type: ignore[no-untyped-def]
    from agentbox.config import Settings
    from agentbox.core.data import SessionStore
    from agentbox.core.definitions import DefinitionLoader
    from agentbox.core.executor import RunExecutor

    (tmp_path / "agentbox.toml").write_text("project='t'\n")
    settings = Settings(
        manifest_path=tmp_path / "agentbox.toml",
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        port=0,
        host="127.0.0.1",
        agents_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
        creds_dir=tmp_path / "creds",
    )
    store = SessionStore(tmp_path / "db.sqlite")
    loader = DefinitionLoader(tmp_path)
    return RunExecutor(store=store, settings=settings, loader=loader)


def test_validate_output_rejects_missing_required(tmp_path: Path) -> None:
    """_validate_output catches missing required field via jsonschema."""
    from agentbox.core.data.manifest import AgentDef, RunnerSpec

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

    ok, err = executor._validate_output(
        json.dumps({"name": "test"}), agent, tmp_path  # missing "value"
    )
    assert not ok
    assert "value" in err

    ok, err = executor._validate_output(
        json.dumps({"name": "test", "value": 5}), agent, tmp_path
    )
    assert ok
    assert err == ""


def test_validate_output_rejects_enum_violation(tmp_path: Path) -> None:
    """_validate_output rejects invalid enum values."""
    from agentbox.core.data.manifest import AgentDef, RunnerSpec

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

    ok, err = executor._validate_output(
        json.dumps({"status": "unknown"}), agent, tmp_path
    )
    assert not ok

    ok, _ = executor._validate_output(json.dumps({"status": "ok"}), agent, tmp_path)
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
