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


class LaunchTargetUnresolved(WorkspaceError, LookupError):
    """Raised when ``WorkspaceService.resolve_launch_target`` cannot determine
    which workspace to use for an interactive launch.

    Maps to exit code 1 via the CLI's ``except LookupError`` handler (same as
    ``WorkspaceNotFound``).  The CLI catches this and renders the canonical
    "No workspace specified…" message.
    """

    DEFAULT_MESSAGE = (
        "No workspace specified and no 'default' workspace defined.\n"
        "Run agentbox ws ls to see available workspaces, "
        "or pass --workspace NAME / --ephemeral."
    )

    def __init__(self) -> None:
        super().__init__(self.DEFAULT_MESSAGE)
