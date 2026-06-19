"""Unit tests for ``core/agents/runtime.py`` — the Agents→Execution facade.

Each function gets one demo()-style sanity check per the plan.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


from agentbox.core.agents.runtime import (
    AgentRuntimeView,
    capture_fragments,
)


class TestAgentRuntimeView:
    def test_from_agent_basic(self, make_agent_def) -> None:
        agent = make_agent_def(id="test.from_agent_basic")
        view = AgentRuntimeView.from_agent(agent, store=None)
        assert view.max_validation_retries == 0
        assert view.max_error_retries == 0
        assert view.output_validation_engine == "both"
        assert view.json_schema is None
        assert view.validators == ()
        assert view.has_schema is False

    def test_has_schema_with_json_schema(self) -> None:
        view = AgentRuntimeView(json_schema={"type": "object"})
        assert view.has_schema is True

    def test_has_schema_with_validators(self) -> None:
        view = AgentRuntimeView(validators=(MagicMock(),))
        assert view.has_schema is True

    def test_from_agent_with_store(self, make_agent_def, mock_store) -> None:
        mock_store.list_prompt_bindings.return_value = []
        agent = make_agent_def(id="test.from_agent_with_store")
        view = AgentRuntimeView.from_agent(agent, store=mock_store)
        assert view.max_validation_retries == 0


class TestCaptureFragments:
    def test_capture_smoke(self, make_agent_def) -> None:
        agent = make_agent_def(id="test.capture_smoke")
        result = capture_fragments(
            agent=agent,
            user_input="hello",
            project_root=Path("/tmp"),
        )
        assert isinstance(result, str)
        assert "hello" in result



