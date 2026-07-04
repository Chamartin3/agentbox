"""Workspace-related exceptions."""

from __future__ import annotations

from agentbox.core.data.errors.base import AgentboxError


class WorkspaceError(AgentboxError):
    """Workspace registry, permission, or sync failure."""


class WorkspaceNotFound(WorkspaceError, LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"unknown workspace {name!r}")
        self.name = name


class WorkspaceExists(WorkspaceError, ValueError):
    def __init__(self, name: str, detail: str | None = None) -> None:
        super().__init__(detail or f"workspace {name!r} already exists")
        self.name = name


class WorkspacePathEscape(WorkspaceError, ValueError):
    def __init__(self, path: str) -> None:
        super().__init__("path escapes workspace")
        self.path = path
