"""Agent branch — manage agent definitions, prompts, versions, tools, and checks.

Tree (≤6 children per node):
agent
├── def       ls  show  new  edit  rm  export
├── prompt    show  edit  log  draft  publish  rollback
├── version   ls  show  new  note  publish  rollback
├── tool      ls  show  grant  revoke
├── check     get  set
└── files     add  rm
"""

from __future__ import annotations

import typer


from agentbox.cli.agent.check import check_app
from agentbox.cli.agent.definition import definition_app
from agentbox.cli.agent.files import files_app
from agentbox.cli.agent.prompt import prompt_app
from agentbox.cli.agent.tool import tool_app
from agentbox.cli.agent.version import version_app

app = typer.Typer(
    name="agent",
    help="Manage agent definitions, prompts, versions, tools, and validation.",
    no_args_is_help=True
)

app.add_typer(definition_app, name="def")
app.add_typer(prompt_app, name="prompt")
app.add_typer(version_app, name="version")
app.add_typer(tool_app, name="tool")
app.add_typer(check_app, name="check")
app.add_typer(files_app, name="files")

__all__ = ["app"]
