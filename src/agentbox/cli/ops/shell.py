"""agentbox shell — drop into a workspace with all configs materialised.

Resolves the workspace exactly like ``agentbox launch``, generates the full
runner config tree into ``<workspace>/.agentbox/generated/`` (persisted, so
you can browse it), renders the env-doc into ``CLAUDE.md`` / ``AGENTS.md``,
and execs ``$SHELL`` (or ``yazi`` with ``--yazi``) at the workspace root.

The intent is parity with what a real run sees: same workdir, same configs,
same env-doc. Use it to inspect/validate that configuration generates the
expected file tree.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer

from agentbox.cli.shared import console
from agentbox.cli.ops.launch import _apply_creds, _resolve_workspace
from agentbox.core.config import load_settings
from agentbox.core.db import Database
from agentbox.core.service.workspaces import launch_runner_configs
from agentbox.core.service import SessionStore
from agentbox.core.workspaces.prep import render_env_doc
from agentbox.core.service import get_agent_def, get_workspace


def shell_cmd(
    agent: str = typer.Argument(..., help="Agent ID whose workspace to enter"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Named workspace or path override"
    ),
    ephemeral: bool = typer.Option(
        False, "--ephemeral", "-e", help="Force an ephemeral (tmp) workspace"
    ),
    yazi: bool = typer.Option(False, "--yazi", help="Exec yazi instead of $SHELL"),
    shell_bin: str | None = typer.Option(
        None, "--shell", help="Shell binary to exec (default: $SHELL or bash)"
    ),
) -> None:
    """Drop into a fully-built work environment for ``agent``.

    Generates configs + env-doc into the workspace, then execs an interactive
    shell at the workspace root. Configs land under
    ``<workspace>/.agentbox/generated/`` and are overwritten each invocation.
    """
    settings = load_settings()
    _db = Database(settings.db_path)
    store = SessionStore(settings.db_path)

    agent_def = get_agent_def(store, agent)
    if agent_def is None:
        console.print(f"[red]Unknown agent:[/red] {agent!r}")
        raise typer.Exit(1)

    workspace_path, is_ephemeral, creds, _ = _resolve_workspace(
        agent_def, workspace, ephemeral, settings
    )

    _apply_creds(creds, settings)

    # Place native runner config in the workspace cwd for the interactive
    # session. ``keep=True`` — the exec'd shell needs it to persist; the
    # service never clobbers the user's own config files.
    launch_cm = launch_runner_configs(
        workspace_path, store=store, settings=settings, keep=True
    )
    launch_cm.__enter__()

    env_doc_rendered = _render_env_doc(settings, workspace, agent_def, workspace_path)

    _print_banner(agent, workspace_path, is_ephemeral, creds, env_doc_rendered)

    if yazi:
        bin_path = shutil.which("yazi")
        if not bin_path:
            console.print("[red]yazi not found on PATH[/red]")
            raise typer.Exit(127)
        argv = [bin_path, str(workspace_path)]
    else:
        bin_path = shell_bin or os.environ.get("SHELL") or "/bin/bash"
        argv = [bin_path, "-i"]

    os.chdir(workspace_path)
    os.execvp(argv[0], argv)


def _render_env_doc(
    settings,
    workspace_override: str | None,
    agent_def,
    workspace_path: Path,
) -> bool:
    """Best-effort env-doc render. Returns True if a doc was written."""
    ws_name = workspace_override or agent_def.workspace
    if not ws_name or ws_name == "<ephemeral>":
        return False
    try:
        _db = Database(settings.db_path)
        store = SessionStore(settings.db_path)
        ws = get_workspace(store, ws_name)
        if not ws:
            return False
        entries = render_env_doc(store, ws.get("id") or ws_name, workspace_path)
        return bool(entries)
    except Exception as exc:
        console.print(f"[yellow]env-doc render skipped:[/yellow] {exc}")
        return False


def _print_banner(
    agent: str,
    workspace_path: Path,
    is_ephemeral: bool,
    creds: str | None,
    env_doc_rendered: bool,
) -> None:
    console.print("━" * 60)
    console.print(f"[bold]agentbox shell[/bold] — [cyan]{agent}[/cyan]")
    console.print("━" * 60)
    console.print(
        f"  workdir:   {workspace_path}{'  (ephemeral)' if is_ephemeral else ''}"
    )
    console.print(
        f"  env-doc:   {'rendered (CLAUDE.md / AGENTS.md)' if env_doc_rendered else 'none'}"
    )
    console.print(f"  creds:     {creds or 'default'}")
    console.print()
    console.print("  Native config (.mcp.json / .claude / opencode.json) is in cwd.")
    console.print("  Exit the shell to return.")
    console.print()
