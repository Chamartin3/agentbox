"""CLI sub-app: agentbox resource — CRUD for the resource repository."""

from __future__ import annotations

import typer

from agentbox.cli.resources.repo.list_ import register_list
from agentbox.cli.resources.repo.create import register_create
from agentbox.cli.resources.repo.inspect import register_inspect
from agentbox.cli.resources.repo.manage import register_manage

resource_app = typer.Typer(
    name="resource",
    help="Manage versioned resources in the resource repository.",
    no_args_is_help=True,
)

register_list(resource_app)
register_create(resource_app)
register_inspect(resource_app)
register_manage(resource_app)
