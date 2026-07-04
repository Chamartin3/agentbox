"""Tests for domain exception hierarchy."""

from __future__ import annotations

from agentbox.core.data.errors import (
    AgentboxError,
    WorkspaceError,
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
)


def test_base_exception_is_exception_subclass() -> None:
    assert issubclass(AgentboxError, Exception)


def test_workspace_error_extends_base() -> None:
    assert issubclass(WorkspaceError, AgentboxError)


def test_workspace_not_found_has_name() -> None:
    err = WorkspaceNotFound("default")
    assert "default" in str(err)
    assert err.name == "default"


def test_workspace_exists_has_name() -> None:
    err = WorkspaceExists("default")
    assert "default" in str(err)
    assert err.name == "default"


def test_workspace_path_escape_has_path() -> None:
    err = WorkspacePathEscape("/etc/passwd")
    assert "path escapes workspace" in str(err)
    assert err.path == "/etc/passwd"
