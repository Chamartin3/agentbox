"""CLI dependency-injection context.

A thin DI seam over the existing ``deps.py`` singleton factories.
Every command group feeds a ``CLIContext`` into ``ctx.obj`` so leaf
commands read ``ctx.obj.<field>`` instead of importing globals.

Also owns the CLI error-handling contract (``handle_cli_errors``) and
the agent resolution helper (``resolve_agent``), which map service
exceptions to coloured ``typer.Exit`` calls.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import typer

from agentbox.core.config import Settings
from agentbox.core.service import AgentDef
from agentbox.core.service import AgentService, DiagnosticsService, EngineService, ExecutionService, EvaluationService, SystemService
from agentbox.core.service.resources import ResourceService
from agentbox.core.service.workspaces import WorkspaceService

from agentbox.cli.shared.deps import (
    get_settings,
    get_agent_service,
    get_diagnostics_service,
    get_execution_service,
    get_engine_service,
    get_evaluation_service,
    get_system_service,
    get_resource_service,
    get_workspace_service,
)
from agentbox.cli.shared.render import console
from agentbox.cli.shared.renderers import (
    AgentRenderer,
    EngineRenderer,
    OpsRenderer,
    RunRenderer,
    SystemRenderer,
    WorkspaceRenderer,
)


# ---------------------------------------------------------------------------
# Error-handling contract
# ---------------------------------------------------------------------------

# Error codes: 1 = not found / expected failure, 2 = invalid input, 3 = upstream


@contextmanager
def handle_cli_errors() -> Iterator[None]:
    """Map known service errors to coloured ``typer.Exit``.

    ``LookupError`` (NotFound) → exit 1, ``ValueError`` (AlreadyExists,
    Invalid) → exit 2, ``RuntimeError`` → exit 3.
    """
    try:
        yield
    except LookupError as exc:
        console.print(f"[red]not found:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ValueError as exc:
        console.print(f"[red]invalid:[/red] {exc}")
        raise typer.Exit(2) from exc
    except RuntimeError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(3) from exc


def resolve_agent(agent_id: str) -> AgentDef:
    """Resolve an agent by id, printing an error and exiting on failure."""
    a = get_agent_service().resolve_agent(agent_id)
    if a is None:
        console.print(f"[red]unknown agent[/red] {agent_id!r}")
        raise typer.Exit(2)
    return a


# ---------------------------------------------------------------------------
# Renderer registry
# ---------------------------------------------------------------------------


@dataclass
class Renderers:
    """Registry of per-domain renderer components, all subclassing Renderer."""

    agent: AgentRenderer
    engine: EngineRenderer
    run: RunRenderer
    workspace: WorkspaceRenderer
    system: SystemRenderer
    ops: OpsRenderer


# ---------------------------------------------------------------------------
# DI context
# ---------------------------------------------------------------------------


@dataclass
class CLIContext:
    """Shared dependency graph for CLI commands."""

    settings: Settings
    render: Renderers
    agents: AgentService
    execution: ExecutionService
    engines: EngineService
    evaluation: EvaluationService
    system: SystemService
    resources: ResourceService
    workspaces: WorkspaceService
    diagnostics: DiagnosticsService


def build_ctx() -> CLIContext:
    """Thin wrapper over ``deps.py`` singleton factories."""
    return CLIContext(
        settings=get_settings(),
        render=Renderers(
            agent=AgentRenderer(),
            engine=EngineRenderer(),
            run=RunRenderer(),
            workspace=WorkspaceRenderer(),
            system=SystemRenderer(),
            ops=OpsRenderer(),
        ),
        agents=get_agent_service(),
        execution=get_execution_service(),
        engines=get_engine_service(),
        evaluation=get_evaluation_service(),
        system=get_system_service(),
        resources=get_resource_service(),
        workspaces=get_workspace_service(),
        diagnostics=get_diagnostics_service(),
    )


def group_callback(ctx: typer.Context) -> None:
    """Attach ``CLIContext`` to ``ctx.obj`` for every command in this group.

    Only builds the context when a subcommand is actually invoked
    (not for bare ``--help``), so help output never triggers DB init.
    """
    if ctx.invoked_subcommand is not None:
        ctx.obj = build_ctx()
