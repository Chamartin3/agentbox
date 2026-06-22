"""Work branch — manage workspaces, files, MCP, permissions, resources, skills.

Tree (≤6 children per node):
work
├── ws        ls  show  new  edit  rm  shell  explore
├── file      gen  skills  edit
├── mcp       show  policy  toggle  refresh  tools
├── perm      get  put
├── res       list  set  dry-run
└── skill     ls  show
"""

from __future__ import annotations

import typer


from agentbox.cli.work.file import file_app
from agentbox.cli.work.mcp import mcp_workspace_app
from agentbox.cli.work.perm import permissions_app
from agentbox.cli.work.res import workspace_resources_app
from agentbox.cli.work.skill import skills_app
from agentbox.cli.work.ws import ws_app

app = typer.Typer(
    name="work",
    help="Manage workspaces: ws, file, mcp, perm, res, skill.",
    no_args_is_help=True
)

app.add_typer(ws_app, name="ws")
app.add_typer(file_app, name="file")
app.add_typer(mcp_workspace_app, name="mcp")
app.add_typer(permissions_app, name="perm")
app.add_typer(workspace_resources_app, name="res")
app.add_typer(skills_app, name="skill")

__all__ = ["app"]
