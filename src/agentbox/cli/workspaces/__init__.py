"""Workspace CLI commands: CRUD, MCP overlay, resource bindings."""

from __future__ import annotations

from agentbox.cli.workspaces.crud import ws_app as app
from agentbox.cli.workspaces.mcp import mcp_workspace_app as _mcp_app
from agentbox.cli.workspaces.resources import workspace_resources_app as _resources_app

app.add_typer(_mcp_app, name="mcp")
app.add_typer(_resources_app, name="resources")

__all__ = ["app"]
