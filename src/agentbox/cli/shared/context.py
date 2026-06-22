"""CLI dependency-injection context.

A thin DI seam over the existing ``deps.py`` singleton factories.
Every command group feeds a ``CliCtx`` into ``ctx.obj`` so leaf
commands read ``ctx.obj.<field>`` instead of importing globals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import typer

from agentbox.cli.shared.deps import get_settings, get_store
from agentbox.cli.shared.render import Renderer

if TYPE_CHECKING:
    from agentbox.core.config import Settings
    from agentbox.core.service import SessionStore


@dataclass
class CliCtx:
    """Shared dependency graph for CLI commands."""
    settings: Settings
    store: SessionStore
    render: Renderer


def build_ctx() -> CliCtx:
    """Thin wrapper over ``deps.py`` singleton factories."""
    return CliCtx(
        settings=get_settings(),
        store=get_store(),
        render=Renderer(),
    )


def group_callback(ctx: typer.Context) -> None:
    """Attach ``CliCtx`` to ``ctx.obj`` for every command in this group.

    Only builds the context when a subcommand is actually invoked
    (not for bare ``--help``), so help output never triggers DB init.
    """
    if ctx.invoked_subcommand is not None:
        ctx.obj = build_ctx()
