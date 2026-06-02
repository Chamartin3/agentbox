"""Tests for ``core/validation.py`` + ``BackendAdapter.validate_output()``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentbox.core.run.validation import (
    ValidationResult,
    extract_json,
    validate_jsonschema,
    validate_output,
    validate_pydantic,
)


# Minimal fake agent — only the attributes validate_output() reads.
class _FakeAgent:
    def __init__(
        self,
        composed_schema: dict | None = None,
        output_schema_path: str | None = None,
        engine: str = "jsonschema",
    ) -> None:
        self._composed_schema = composed_schema
        # Mirror the shape AgentDef exposes via PythonAgentConfig.from_agent.
        self.runner = _FakeRunner(output_schema_path)
        self._engine = engine
        # ExecutionConfig.from_agent reads .runner.output_validation_engine
        self.runner.output_validation_engine = engine
        self.composition = None

    @property
    def __dict__(self) -> dict[str, Any]:  # type: ignore[override]
        return {"_composed_schema": self._composed_schema}


class _FakeRunner:
    def __init__(
        self,
        output_schema_path: str | None,
    ) -> None:
        self.output_schema_path = output_schema_path
        self.output_validation_engine = "jsonschema"
        # PythonAgentConfig.from_agent inspects these too:
        self.kind = "token"
        self.agent_module = None
        self.deps_factory = None
        self.max_validation_retries = 0
        self.max_error_retries = 0


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
    agent = _FakeAgent(composed_schema=None, output_schema_path=None)
    result = validate_output(agent, tmp_path, '{"anything": 1}')
    assert result == ValidationResult(ok=True, engine="off")


def test_validate_output_empty_when_schema_required(tmp_path: Path) -> None:
    """A schema is configured but output is empty → reportable failure."""
    agent = _FakeAgent(composed_schema=_SCHEMA)
    result = validate_output(agent, tmp_path, "")
    assert not result.ok
    assert result.engine == "none"
    assert "empty" in result.error


def test_validate_output_uses_composed_schema(tmp_path: Path) -> None:
    """Composed schema beats reading from disk — works for DB-only agents."""
    agent = _FakeAgent(composed_schema=_SCHEMA, engine="jsonschema")
    result = validate_output(agent, tmp_path, '{"name": "x"}')
    assert result.ok
    assert result.engine == "jsonschema"


def test_validate_output_falls_back_to_disk_schema(tmp_path: Path) -> None:
    """When _composed_schema isn't set, load from runner.output_schema_path."""
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(_SCHEMA))
    agent = _FakeAgent(
        composed_schema=None, output_schema_path="schema.json", engine="jsonschema"
    )
    result = validate_output(agent, tmp_path, '{"name": "x"}')
    assert result.ok


def test_validate_output_missing_schema_file(tmp_path: Path) -> None:
    agent = _FakeAgent(composed_schema=None, output_schema_path="nope.json")
    result = validate_output(agent, tmp_path, '{"name": "x"}')
    assert not result.ok
    assert result.engine == "none"
    assert "not found" in result.error


def test_validate_output_both_engines(tmp_path: Path) -> None:
    """``both`` runs jsonschema first then pydantic — failure attribution
    matters for the retry prompt."""
    agent = _FakeAgent(composed_schema=_SCHEMA, engine="both")
    result = validate_output(agent, tmp_path, '{"name": "x"}')
    assert result.ok
    assert result.engine == "both"


def test_validate_pydantic_smoke() -> None:
    """Pydantic validation runs via the shared helper. Single smoke test —
    deep coverage lives in ``test_pydantic_validate``."""
    result = validate_pydantic('{"name": "x"}', _SCHEMA)
    assert result.engine == "pydantic"


def test_backend_adapter_default_validate_output(tmp_path: Path) -> None:
    """``BackendAdapter`` default impl delegates to validation.validate_output."""
    from collections.abc import AsyncIterator

    from agentbox.core.data import RunEvent
    from agentbox.core.run.backends.base import BackendAdapter, RenderedConfig

    class _Stub(BackendAdapter):
        name = "stub"

        def render(
            self, agent, workdir, mcp_tools=None, creds=None, runner_config=None
        ):  # type: ignore[no-untyped-def]
            return RenderedConfig()

        async def run(self, rendered, input, run_id) -> AsyncIterator[RunEvent]:  # type: ignore[override]
            if False:
                yield  # pragma: no cover

    adapter = _Stub()
    agent = _FakeAgent(composed_schema=_SCHEMA)
    result = adapter.validate_output(agent, tmp_path, '{"name": "x"}')
    assert result.ok
    assert result.engine == "jsonschema"
