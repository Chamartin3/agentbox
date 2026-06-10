from __future__ import annotations

import hashlib
import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from agentbox.cli._common import console, resolve_agent
from agentbox.cli._deps import get_settings, get_store
from agentbox.cli.agents._common import _coerce, _set_dotted
from agentbox.core.service import (
    AgentDef,
    build_agent_snapshot,
    build_config_json_payload,
    create_agent,
    create_agent_version,
    get_agent_def,
    get_agent_runner_profile,
    latest_agent_version,
    soft_delete_agent,
)
from agentbox.core.service.agents import (
    list_all_agents,
)

agent_app = typer.Typer(
    name="agent",
    help="Inspect agent definitions and prompts.",
    no_args_is_help=True,
)


@agent_app.command("ls")
def agent_ls(
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """List agents registered in the DB."""
    store = get_store()
    rows = list_all_agents(store=store)

    if json_output:
        console.print(
            json.dumps(
                [a.model_dump(mode="json") for a in rows], indent=2
            )
        )
        return

    if not rows:
        console.print("[yellow]No agents registered.[/yellow]")
        return

    table = Table(
        title="Agents",
        title_style="bold",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Runner", style="cyan")
    table.add_column("Model", style="dim")
    table.add_column("Session", style="dim")
    table.add_column("Workspace", style="dim")
    table.add_column("Description")

    for a in rows:
        ws_display = (
            "[yellow]<ephemeral>[/yellow]"
            if a.workspace == "<ephemeral>"
            else (a.workspace or "[dim]auto[/dim]")
        )
        # Model is resolved via the bound runner profile — the legacy
        # ``runner.model`` field is no longer surfaced.
        profile = get_agent_runner_profile(store, a.id)
        model_display = (profile.model if profile else None) or "[dim]default[/dim]"
        table.add_row(
            a.id,
            a.runner.kind,
            model_display,
            a.session_mode,
            ws_display,
            a.description or "",
        )
    console.print(table)


@agent_app.command("show")
def agent_show(agent_id: str) -> None:
    """Show the full resolved AgentDef for an agent."""
    a = resolve_agent(agent_id)

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("id", a.id)
    meta.add_row("description", a.description or "—")
    meta.add_row("source_format", a.source_format.value if a.source_format else "—")
    meta.add_row("source_path", str(a.source_path) if a.source_path else "—")
    meta.add_row("tags", ", ".join(a.tags) if a.tags else "—")
    console.print(Panel(meta, title="Meta", border_style="cyan"))

    runner = Table.grid(padding=(0, 2))
    runner.add_column(style="dim", justify="right")
    runner.add_column()
    runner.add_row("kind", a.runner.kind)
    # The model is owned by the bound runner profile. The legacy
    # ``runner.model`` field is no longer displayed — see the "Runner
    # profile" panel below for the authoritative model.
    runner.add_row("timeout", f"{a.runner.timeout_seconds}s")
    runner.add_row(
        "allowed_tools",
        ", ".join(a.runner.allowed_tools) if a.runner.allowed_tools else "—",
    )
    runner.add_row("mcp_config_path", a.runner.mcp_config_path or "—")
    console.print(Panel(runner, title="Runner", border_style="green"))

    profile = get_agent_runner_profile(get_store(), a.id)
    rp = Table.grid(padding=(0, 2))
    rp.add_column(style="dim", justify="right")
    rp.add_column()
    if profile is None:
        rp.add_row("bound profile", "[dim](none — system default)[/dim]")
    else:
        rp.add_row("id", profile.id)
        rp.add_row("name", profile.name)
        rp.add_row("backend", profile.backend)
        rp.add_row("provider", profile.provider or "—")
        rp.add_row("model", profile.model or "—")
    console.print(Panel(rp, title="Runner profile", border_style="green"))

    ws = Table.grid(padding=(0, 2))
    ws.add_column(style="dim", justify="right")
    ws.add_column()
    ws.add_row("workspace", a.workspace or "[dim]auto[/dim]")
    ws.add_row("session_mode", a.session_mode)
    ws.add_row("headless", str(a.headless))
    ws.add_row("claude_agent", str(a.claude_agent))
    console.print(Panel(ws, title="Workspace", border_style="blue"))

    servers = get_store().get_project_mcp_servers()
    if servers:
        mcp_list = Table.grid(padding=(0, 2))
        mcp_list.add_column(style="dim")
        mcp_list.add_column()
        for s in servers:
            mcp_list.add_row(s.name, s.url or " ".join(s.command or []))
        console.print(Panel(mcp_list, title="MCP Servers", border_style="yellow"))


# ---------------------------------------------------------------------------
# Plan 18 — DB-only write commands. These talk to the store directly so they
# work in offline contexts (no HTTP server required).
# ---------------------------------------------------------------------------


@agent_app.command("create")
def agent_create(
    name: str = typer.Option(
        "",
        "--name",
        "-n",
        help="Agent id + display name. Creates a minimal agent with sensible defaults.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to inline JSON config (full AgentDef shape).",
    ),
    author: str = typer.Option(
        "cli",
        "--author",
        help="Author identifier.",
    ),
    changelog: str = typer.Option(
        "initial draft", "--changelog", help="Changelog (min 3 chars)."
    ),
) -> None:
    """Create a new DB-only agent.

    Use ``--config`` to load a full AgentDef JSON file, or ``--name`` to
    create a minimal agent with sensible defaults (no disk file required).
    """
    if config is not None:
        data = json.loads(config.read_text(encoding="utf-8"))
        try:
            agent_def = AgentDef.model_validate(data)
        except Exception as exc:
            console.print(f"[red]invalid AgentDef:[/red] {exc}")
            raise typer.Exit(2) from exc
    elif name:
        agent_def = AgentDef(id=name, description=name)
    else:
        console.print("[red]either --config or --name is required[/red]")
        raise typer.Exit(2)

    store = get_store()
    if latest_agent_version(store, agent_def.id) is not None:
        console.print(f"[red]agent {agent_def.id!r} already exists[/red]")
        raise typer.Exit(1)

    rec = create_agent(
        store,
        agent_id=agent_def.id,
        config_json={
            **agent_def.model_dump(mode="json", exclude_none=True),
            **build_config_json_payload(agent_def),
        },
        prompt_content=agent_def.prompt,
        author=author,
        changelog=changelog,
        source="cli",
        sync_mode="off",
        export_to_disk=False,
    )
    console.print(
        f"[green]created[/green] {agent_def.id!r} v{rec['version']} "
        f"(draft, version_id={rec['id']})"
    )


@agent_app.command("edit")
def agent_edit(
    agent_id: str,
    set_: list[str] = typer.Option(
        [],
        "--set",
        "-s",
        help="dotted=value pairs, e.g. runner.kind=token. Repeatable.",
    ),
    author: str = typer.Option("cli", "--author"),
    changelog: str = typer.Option("cli edit", "--changelog"),
) -> None:
    """Edit an agent in the DB. Each ``--set k=v`` overrides a field.

    Values are parsed as JSON when possible (so ``--set tags='["x","y"]'``
    works), else stored verbatim as a string.
    """
    if not set_:
        console.print("[red]nothing to set; pass --set k=v[/red]")
        raise typer.Exit(2)

    store = get_store()
    settings = get_settings()
    current = get_agent_def(store, agent_id)
    if current is None:
        console.print(f"[red]agent {agent_id!r} not found[/red]")
        raise typer.Exit(1)

    merged = current.model_dump(mode="python")
    for pair in set_:
        if "=" not in pair:
            console.print(f"[red]bad --set pair: {pair!r}[/red]")
            raise typer.Exit(2)
        k, v = pair.split("=", 1)
        _set_dotted(merged, k.strip(), _coerce(v.strip()))

    try:
        updated = AgentDef.model_validate(merged)
    except Exception as exc:
        console.print(f"[red]validation failed:[/red] {exc}")
        raise typer.Exit(2) from exc

    updated.source_path = current.source_path
    updated.source_format = current.source_format
    snapshot = build_agent_snapshot(updated)
    prompt_text = ""
    if updated.prompt_path:
        try:
            prompt_text = updated.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""

    rec = create_agent_version(
        store,
        agent_id=updated.id,
        source_path=str(updated.source_path) if updated.source_path else "",
        source_format=(
            updated.source_format.value if updated.source_format else "unknown"
        ),
        content_snapshot=snapshot,
        prompt_snapshot=prompt_text,
        content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
        author=author,
        changelog=changelog,
        files=None,
    )
    console.print(
        f"[green]new version[/green] {updated.id!r} v{rec['version']} "
        "— publish with `agent publish`"
    )


@agent_app.command("delete")
def agent_delete(
    agent_id: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Soft-delete an agent. Version history is retained."""
    if not yes:
        confirm = typer.confirm(f"Soft-delete agent {agent_id!r}? (history retained)")
        if not confirm:
            raise typer.Exit(0)
    store = get_store()
    result = soft_delete_agent(store, agent_id)
    if result is None:
        console.print(f"[red]agent {agent_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[green]deleted[/green] {agent_id!r}")
