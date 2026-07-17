"""Tests for AgentDef and related manifest pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentbox.core.data.manifests.agents import AgentDef, CompositionConfig
from agentbox.core.data.manifests.engines import RunnerSpec
from agentbox.core.data.manifests.system import ProjectManifest
from agentbox.core.data.manifests.workspaces import WorkspaceDef


class TestRunnerSpec:
    def test_minimal(self) -> None:
        spec = RunnerSpec(kind="claude_code")
        assert spec.kind == "claude_code"
        assert spec.timeout_seconds == 1200

    def test_with_all_fields(self) -> None:
        spec = RunnerSpec(
            kind="token",
            timeout_seconds=120,
            max_error_retries=2,
            max_validation_retries=3,
            output_validation_engine="jsonschema",
        )
        assert spec.timeout_seconds == 120
        assert spec.max_error_retries == 2
        assert spec.max_validation_retries == 3
        assert spec.output_validation_engine == "jsonschema"

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RunnerSpec(kind=123)  # type: ignore[arg-type]


class TestAgentDef:
    def test_minimal(self) -> None:
        agent = AgentDef(id="my-agent")
        assert agent.id == "my-agent"
        assert agent.description == ""
        assert agent.tags == []
        assert agent.session_mode == "headless"

    def test_description_defaults_to_empty(self) -> None:
        agent = AgentDef(id="a")
        assert agent.description == ""

    def test_runner_defaults_to_token(self) -> None:
        agent = AgentDef(id="a")
        assert agent.runner.kind == "token"

    def test_with_composition(self) -> None:
        agent = AgentDef(
            id="agent-comp",
            description="With composition",
            runner=RunnerSpec(kind="claude_code"),
            composition=CompositionConfig(
                system="You are helpful.",
                user_template="Process {{input}}",
            ),
        )
        assert agent.composition is not None
        assert agent.composition.system == "You are helpful."

    def test_webhook_url_optional(self) -> None:
        agent = AgentDef(id="a", description="d", runner=RunnerSpec(kind="claude_code"))
        assert agent.webhook_url is None

    def test_unsupported_backends_default_empty(self) -> None:
        agent = AgentDef(id="a", description="d", runner=RunnerSpec(kind="claude_code"))
        assert agent.unsupported_backends == []


class TestWorkspaceDef:
    def test_minimal(self) -> None:
        ws = WorkspaceDef(name="my-ws", path="/tmp/ws")
        assert ws.name == "my-ws"
        assert ws.path == "/tmp/ws"
        assert ws.description == ""


class TestProjectManifest:
    def test_minimal(self) -> None:
        pm = ProjectManifest()
        assert pm.workspaces == []
        assert pm.agents == []
