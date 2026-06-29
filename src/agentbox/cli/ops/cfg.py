from __future__ import annotations

import os

import typer

from agentbox.cli.shared import CliCtx
# TODO(cli-arch): WorkspaceService workenv methods (plan 089)
from agentbox.core import workspaces as ws_mod  # noqa: E402  # TODO(cli-arch)
from agentbox.core.service.agents import list_all_agents  # noqa: E402  # TODO(cli-arch)

cfg_app = typer.Typer(
    name="cfg",
    help="Inspect resolved settings and generated runner configs.",
    no_args_is_help=True,
)


@cfg_app.command("show")
def cfg_show(ctx: typer.Context) -> None:
    """Show resolved Settings + AGENTBOX_* environment variables."""
    obj: CliCtx = ctx.obj
    settings = obj.settings

    s_table = obj.render.ops.grid()
    for field in (
        "manifest_path",
        "data_dir",
        "db_path",
        "port",
        "host",
        "completion_webhook_url",
    ):
        val = getattr(settings, field, None)
        s_table.add_row(field, str(val) if val is not None else "\u2014")
    for prop in (
        "project_root",
        "workspaces_root",
        "runs_dir",
        "sessions_dir",
        "mcp_cache_dir",
    ):
        val = getattr(settings, prop, None)
        s_table.add_row(prop, str(val) if val else "\u2014")

    obj.render.ops.panel(s_table, title="Settings", border="cyan")

    env_table = obj.render.ops.grid()
    for key in sorted(os.environ):
        if key.startswith("AGENTBOX_"):
            env_table.add_row(key, os.environ[key])
    obj.render.ops.panel(env_table, title="AGENTBOX_* environment", border="green")


@cfg_app.command("paths")
def cfg_paths(ctx: typer.Context) -> None:
    """Show all important paths as a tree."""
    obj: CliCtx = ctx.obj
    obj.render.ops.cfg_tree(
        obj.settings,
        ws_mod.resolve_path,
        list_all_agents,
        obj.store,
    )
