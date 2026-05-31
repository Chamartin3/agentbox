"""Tests for domain exception hierarchy."""

from __future__ import annotations

from agentbox.core.exceptions import (
    AgentboxError,
    AgentNotFoundError,
    BackendSelectionError,
    ConfigurationError,
    InconsistentSchemaError,
    PromptVersionError,
    ResourceSchemaError,
    RunSetupError,
    SnapshotError,
    WebhookDeliveryError,
    WorkspaceError,
)


def test_base_exception_is_exception_subclass() -> None:
    assert issubclass(AgentboxError, Exception)


def test_all_errors_extend_base() -> None:
    for cls in (
        ConfigurationError,
        ResourceSchemaError,
        InconsistentSchemaError,
        BackendSelectionError,
        RunSetupError,
        SnapshotError,
        WebhookDeliveryError,
        WorkspaceError,
        PromptVersionError,
        AgentNotFoundError,
    ):
        assert issubclass(cls, AgentboxError), f"{cls.__name__} not a subclass of AgentboxError"


def test_configuration_errors_are_configuration_subclass() -> None:
    assert issubclass(ResourceSchemaError, ConfigurationError)
    assert issubclass(InconsistentSchemaError, ConfigurationError)


def test_agent_not_found_is_direct_subclass_of_base() -> None:
    assert AgentNotFoundError.__bases__ == (AgentboxError,)


def test_backend_selection_error_has_message() -> None:
    err = BackendSelectionError("no backend for agent-1")
    assert "agent-1" in str(err)


def test_run_setup_error_is_agentbox_subclass() -> None:
    err = RunSetupError("workdir missing")
    assert isinstance(err, AgentboxError)


def test_webhook_delivery_error() -> None:
    err = WebhookDeliveryError("POST failed")
    assert isinstance(err, AgentboxError)


def test_snapshot_error() -> None:
    err = SnapshotError("failed to persist")
    assert isinstance(err, AgentboxError)
