from __future__ import annotations

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.cli._common import console, resolve_agent
from agentbox.core import prompts

agent_app = typer.Typer(
    name="agent",
    help="Inspect agent definitions and prompts.",
    no_args_is_help=True,
)


@agent_app.command("ls")
def agent_ls() -> None:
    """List agents declared in the project manifest."""
    rows = get_loader().load().agents
    if not rows:
        console.print(
            "[yellow]No agents declared.[/yellow] Create an agentbox.toml at the project root."
        )
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
    table.add_column("Guardrails", justify="right", style="magenta")
    table.add_column("Description")

    for a in rows:
        ws_display = (
            "[yellow]<ephemeral>[/yellow]"
            if a.workspace == "<ephemeral>"
            else (a.workspace or "[dim]auto[/dim]")
        )
        table.add_row(
            a.id,
            a.runner.kind,
            a.runner.model or "-",
            a.session_mode,
            ws_display,
            str(len(a.guardrails)),
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
    runner.add_row("model", a.runner.model or "—")
    runner.add_row("timeout", f"{a.runner.timeout_seconds}s")
    runner.add_row(
        "allowed_tools",
        ", ".join(a.runner.allowed_tools) if a.runner.allowed_tools else "—",
    )
    runner.add_row("mcp_config_path", a.runner.mcp_config_path or "—")
    console.print(Panel(runner, title="Runner", border_style="green"))

    ws = Table.grid(padding=(0, 2))
    ws.add_column(style="dim", justify="right")
    ws.add_column()
    ws.add_row("workspace", a.workspace or "[dim]auto[/dim]")
    ws.add_row("session_mode", a.session_mode)
    ws.add_row("headless", str(a.headless))
    ws.add_row("claude_agent", str(a.claude_agent))
    console.print(Panel(ws, title="Workspace", border_style="blue"))

    if a.guardrails:
        gt = Table(header_style="bold magenta", padding=(0, 1))
        gt.add_column("Name")
        gt.add_column("Options")
        for g in a.guardrails:
            opts = (
                ", ".join(f"{k}={v}" for k, v in g.options.items())
                if g.options
                else "—"
            )
            gt.add_row(g.name, opts)
        console.print(Panel(gt, title="Guardrails", border_style="magenta"))

    manifest = get_loader().load()
    if manifest.mcp_servers:
        mcp_list = Table.grid(padding=(0, 2))
        mcp_list.add_column(style="dim")
        mcp_list.add_column()
        for s in manifest.mcp_servers:
            mcp_list.add_row(s.name, s.url or " ".join(s.command or []))
        console.print(Panel(mcp_list, title="MCP Servers", border_style="yellow"))


@agent_app.command("prompt")
def agent_prompt(
    agent_id: str,
    version: int | None = typer.Option(
        None, "--version", help="Prompt version to display"
    ),
) -> None:
    """Print the agent's system prompt."""
    a = resolve_agent(agent_id)
    settings = get_settings()
    store = get_store()

    if version is not None:
        committed = store.get_prompt_version(agent_id, version)
        if committed is None:
            console.print(
                f"[red]version {version} not found for agent {agent_id!r}[/red]"
            )
            raise typer.Exit(2)
        content = committed["content"]
    else:
        doc = prompts.read_versioned(a, settings.project_root, store)
        content = doc.content

    if not content:
        console.print("[yellow]No prompt content for this agent.[/yellow]")
        return

    console.print(Syntax(content, "markdown", theme="ansi_dark"))
