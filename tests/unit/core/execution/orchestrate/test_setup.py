"""Unit tests for RunSetup and helpers in orchestrate/setup.py.

Covers:
- _composed_view: None input, field mapping from mock composed object
- NoBackendAvailable: attributes and message format
- RunSetup.resolve_agent_tool_grants: returns grants from store, swallows exception
- RunSetup.select_backend: raises NoBackendAvailable when no backend candidates;
  delegates to adapter when backend_override is supplied
- RunSetup.prepare_workdir: named workspace (non-ephemeral) path and no session
  created; ephemeral stateless creates a temp dir

Fixtures from the dir-level conftest are reused where available (``make_agent``).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.core.execution.orchestrate.setup import (
    NoBackendAvailable,
    RunSetup,
    SetupManagers,
    _composed_view,
)
from agentbox.core.data import ComposedView


def _make_setup(mock_store: MagicMock, mcp_registry: object = None) -> RunSetup:
    """Build a RunSetup from mock_store manager attributes."""
    return RunSetup(
        SetupManagers(
            workspaces=mock_store.workspaces,
            sessions=mock_store.sessions,
            agent_tool_grants=mock_store.agent_tool_grants,
            workspace_file_resource_bindings=mock_store.workspace_file_resource_bindings,
            workspace_mcp_policies=mock_store.workspace_mcp_policies,
            workspace_mcp_overrides=mock_store.workspace_mcp_overrides,
            workspace_mcp_tool_overrides=mock_store.workspace_mcp_tool_overrides,
            agent_prompt_resource_bindings=mock_store.agent_prompt_resource_bindings,
            resource_versions=mock_store.resource_versions,
            resource_blobs=mock_store.resource_blobs,
        ),
        MagicMock(),
        mcp_registry,
    )

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _composed_view
# ---------------------------------------------------------------------------


class TestComposedView:
    def test_none_returns_none(self) -> None:
        """_composed_view(None) must return None — no composed config is valid."""
        assert _composed_view(None) is None

    def test_maps_system_and_schema_fields(self) -> None:
        """_composed_view transfers system/schema from the composed object."""
        composed = MagicMock()
        composed.system = "You are a helpful assistant."
        composed.system_base = "base instructions"
        composed.schema = {"type": "object"}
        composed.input_schema = None
        composed.user = "Hello"
        composed.references = []
        composed.bundle_sha = "abc123"
        composed.validation_mode = "strict"

        result = _composed_view(composed)

        assert isinstance(result, ComposedView)
        assert result.system == "You are a helpful assistant."
        assert result.schema == {"type": "object"}
        assert result.bundle_sha == "abc123"
        assert result.validation_mode == "strict"

    def test_maps_references_as_tuple(self) -> None:
        """_composed_view must convert the references sequence to a tuple of ComposedReferenceView."""
        composed = MagicMock()
        composed.system = None
        composed.system_base = None
        composed.schema = None
        composed.input_schema = None
        composed.user = None
        composed.bundle_sha = None
        composed.validation_mode = None

        ref = MagicMock()
        ref.path = "/some/path"
        ref.heading = "## Resources"
        ref.content = "resource body"
        composed.references = [ref]

        result = _composed_view(composed)

        assert result is not None
        assert len(result.references) == 1
        assert result.references[0].path == "/some/path"
        assert result.references[0].heading == "## Resources"


# ---------------------------------------------------------------------------
# NoBackendAvailable
# ---------------------------------------------------------------------------


class TestNoBackendAvailable:
    def test_attributes_set_correctly(self) -> None:
        """NoBackendAvailable must expose agent_id and attempted as attributes."""
        exc = NoBackendAvailable(agent_id="my-agent", attempted=["claude_code"])

        assert exc.agent_id == "my-agent"
        assert exc.attempted == ["claude_code"]

    def test_message_contains_agent_id(self) -> None:
        """The error message must include the agent_id string."""
        exc = NoBackendAvailable(agent_id="agent-xyz", attempted=[])

        assert "agent-xyz" in str(exc)

    def test_is_runtime_error(self) -> None:
        """NoBackendAvailable is a RuntimeError subclass."""
        exc = NoBackendAvailable(agent_id="a", attempted=[])

        assert isinstance(exc, RuntimeError)


# ---------------------------------------------------------------------------
# RunSetup.resolve_agent_tool_grants
# ---------------------------------------------------------------------------


class TestResolveAgentToolGrants:
    def test_returns_grants_from_store(self, mock_store: MagicMock) -> None:
        """resolve_agent_tool_grants returns the non-empty set from db.agent_tool_grants.list_for_agent."""
        mock_store.agent_tool_grants.list_for_agent.return_value = [
            {"tool_name": "shell.exec"},
            {"tool_name": "fs.read"},
        ]
        setup = _make_setup(mock_store)

        result = setup.resolve_agent_tool_grants("agent-1")

        assert result == {"shell.exec", "fs.read"}
        mock_store.agent_tool_grants.list_for_agent.assert_called_once_with("agent-1")

    def test_returns_none_when_store_raises(self, mock_store: MagicMock) -> None:
        """resolve_agent_tool_grants swallows store exceptions and returns None."""
        mock_store.agent_tool_grants.list_for_agent.side_effect = RuntimeError("permission denied")
        setup = _make_setup(mock_store)

        result = setup.resolve_agent_tool_grants("agent-2")

        assert result is None

    def test_returns_none_when_grants_are_empty(self, mock_store: MagicMock) -> None:
        """resolve_agent_tool_grants returns None when the store returns an empty list."""
        mock_store.agent_tool_grants.list_for_agent.return_value = []
        setup = _make_setup(mock_store)

        result = setup.resolve_agent_tool_grants("agent-3")

        assert result is None


# ---------------------------------------------------------------------------
# RunSetup.select_backend
# ---------------------------------------------------------------------------


class TestSelectBackend:
    def test_raises_when_no_backend_candidates(
        self, mock_store: MagicMock, tmp_path: Path, make_agent: MagicMock
    ) -> None:
        """select_backend raises NoBackendAvailable when neither backend_override nor
        runner_config is provided — no candidates means no adapter can be tried."""
        setup = _make_setup(mock_store)
        agent = make_agent()
        agent.id = "test-agent"
        agent.workspace = None

        with pytest.raises(NoBackendAvailable) as exc_info:
            setup.select_backend(
                agent,
                tmp_path,
                backend_override=None,
                runner_config=None,
            )

        assert exc_info.value.agent_id == "test-agent"
        assert exc_info.value.attempted == []

    def test_raises_when_backend_override_not_registered(
        self,
        mock_store: MagicMock,
        tmp_path: Path,
        make_agent: MagicMock,
    ) -> None:
        """select_backend raises NoBackendAvailable when the named backend is not registered."""
        setup = _make_setup(mock_store)
        agent = make_agent()
        agent.id = "agent-no-backend"
        agent.workspace = None

        with (
            patch(
                "agentbox.core.execution.orchestrate.setup.resolve_engine",
                side_effect=KeyError("no-such-backend"),
            ),
            patch(
                "agentbox.core.execution.orchestrate.setup.resolve_workspace_callables",
                return_value=[],
            ),
            pytest.raises(NoBackendAvailable) as exc_info,
        ):
            setup.select_backend(
                agent,
                tmp_path,
                backend_override="no-such-backend",
            )

        assert "no-such-backend" in exc_info.value.attempted

    def test_returns_adapter_and_rendered_config(
        self,
        mock_store: MagicMock,
        tmp_path: Path,
        make_agent: MagicMock,
    ) -> None:
        """select_backend returns the adapter and its rendered config when the backend resolves."""
        setup = _make_setup(mock_store)
        agent = make_agent()
        agent.id = "agent-with-backend"
        agent.workspace = None

        mock_adapter = MagicMock()
        mock_rendered = MagicMock()
        mock_adapter.render.return_value = mock_rendered

        with (
            patch(
                "agentbox.core.execution.orchestrate.setup.resolve_engine",
                return_value=mock_adapter,
            ),
            patch(
                "agentbox.core.execution.orchestrate.setup.resolve_workspace_callables",
                return_value=[],
            ),
        ):
            adapter, rendered = setup.select_backend(
                agent,
                tmp_path,
                backend_override="my-backend",
            )

        assert adapter is mock_adapter
        assert rendered is mock_rendered


# ---------------------------------------------------------------------------
# RunSetup.prepare_workdir — named workspace (non-ephemeral)
# ---------------------------------------------------------------------------


class TestPrepareWorkdir:
    def test_named_workspace_returns_resolved_path_and_session_id(
        self,
        mock_store: MagicMock,
        tmp_path: Path,
        make_agent: MagicMock,
    ) -> None:
        """prepare_workdir with a named workspace returns the resolved path unchanged."""
        setup = _make_setup(mock_store)
        agent = make_agent(workspace="production-ws", session_mode="stateless")
        expected_path = tmp_path / "production-ws"

        with patch(
            "agentbox.core.execution.orchestrate.setup.resolve_path",
            return_value=(expected_path, False),  # (path, ephemeral=False)
        ):
            path, session_id = setup.prepare_workdir(agent, session_id="sess-1")

        assert path == expected_path
        assert session_id == "sess-1"
        # db.sessions.create_session must not be called to create a session for a named workspace
        mock_store.sessions.create_session.assert_not_called()
