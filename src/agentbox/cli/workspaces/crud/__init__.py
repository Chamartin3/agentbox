"""Workspace CRUD CLI commands.

Re-exports ``ws_app`` so callers that do
``from agentbox.cli.workspaces.crud import ws_app`` continue to work.
"""

from __future__ import annotations

import typer

from agentbox.cli.workspaces.crud._app import ws_app as ws_app

# Import command modules to register their commands on ws_app.
import agentbox.cli.workspaces.crud.core  # noqa: F401
import agentbox.cli.workspaces.crud.registry  # noqa: F401
import agentbox.cli.workspaces.crud.files  # noqa: F401
import agentbox.cli.workspaces.crud.shell  # noqa: F401
from agentbox.cli.workspaces.crud.shell import ws_shell


@ws_app.callback()
def _ws_default(ctx: typer.Context) -> None:
    """Default: open a shell in the default workspace."""
    if ctx.invoked_subcommand is None:
        ws_shell(name=None)


__all__ = ["ws_app"]
