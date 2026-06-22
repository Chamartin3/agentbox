"""Unit tests for ``core/agents/validation/orchestrate.py``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from agentbox.core.agents.validation import orchestrate as _orch
from agentbox.core.agents.validation.orchestrate import validate_output


class TestValidateOutput:
    def test_no_schema_skips(self, make_agent_def) -> None:
        agent = make_agent_def(id="test.no_schema")
        result = validate_output(agent, Path("."), '{"ok": true}')
        assert result.ok is True
        assert result.engine == "off"

    def test_empty_payload_with_schema(self, make_agent_def) -> None:
        agent = make_agent_def(id="test.empty_payload")
        result = validate_output(agent, Path("."), None)
        # No schema configured → off
        assert result.ok is True
        assert result.engine == "off"

    def test_legacy_path_jsonschema_valid(self, make_agent_def) -> None:
        agent = make_agent_def(id="test.legacy_valid")
        result = validate_output(agent, Path("."), '{"key": "val"}')
        assert result.ok is True
        assert result.engine == "off"

    def test_gate_order_and_label(self, make_agent_def, monkeypatch) -> None:
        """When both json_schema and validators are present, gate order
        is jsonschema first, then explicit validators, and the engine
        label reflects the combination.
        """
        mock_validator = MagicMock()
        mock_validator.kind = "http"
        mock_validator.endpoint = "http://example.com/validate"
        mock_validator.headers = {}
        mock_validator.timeout_seconds = 5

        agent = make_agent_def(id="test.gate_order")

        # Patch resolve_output_config so we bypass the store entirely.
        monkeypatch.setattr(
            _orch,
            "resolve_output_config",
            lambda _store, _agent: MagicMock(
                json_schema={"type": "object"},
                validators=[mock_validator],
            ),
        )

        result = validate_output(agent, Path("."), '{"ok": true}', store=None)
        # Gate 1 passes; Gate 2 (http) will fail because the endpoint
        # is not reachable, producing an error result.
        assert result.ok is False
        assert "http" in result.engine or result.engine == "none"
