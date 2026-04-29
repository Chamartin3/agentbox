"""Tests for validation engine selection in the executor."""

from __future__ import annotations

import json
from pathlib import Path

from agentbox.core.data.manifest import AgentDef, RunnerSpec


def _make_executor(tmp_path: Path):
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
        agents_bundle_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
    )
    store = SessionStore(tmp_path / "db.sqlite")
    loader = DefinitionLoader(tmp_path)
    return RunExecutor(store=store, settings=settings, loader=loader)


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
        executor = _make_executor(tmp_path)
        ok, err, via = executor._validate_output(_VALID, agent, tmp_path)
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
        executor = _make_executor(tmp_path)
        ok, err, via = executor._validate_output(_INVALID, agent, tmp_path)
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
        executor = _make_executor(tmp_path)
        ok, err, via = executor._validate_output(_VALID, agent, tmp_path)
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
        executor = _make_executor(tmp_path)
        ok, err, via = executor._validate_output(_INVALID, agent, tmp_path)
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
        executor = _make_executor(tmp_path)
        ok, err, via = executor._validate_output(_VALID, agent, tmp_path)
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
        executor = _make_executor(tmp_path)
        ok, err, via = executor._validate_output(_INVALID, agent, tmp_path)
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
        executor = _make_executor(tmp_path)
        ok, err, via = executor._validate_output(_VALID, agent, tmp_path)
        assert ok
        assert via == "both"
