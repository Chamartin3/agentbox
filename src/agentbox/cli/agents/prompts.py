"""agents prompts — manage per-agent system prompts with versioning."""

from __future__ import annotations

import typer
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli._deps import get_loader, get_settings, get_store
from agentbox.cli._common import console
from agentbox.core.service.prompts import (
    AgentNotFound,
    PromptError,
    get_prompt,
    get_version,
    list_versions,
    publish,
    put_prompt,
    rollback,
    save_draft,
)

prompts_app = typer.Typer(
    name="prompts",
    help="Manage versioned system prompts.",
    no_args_is_help=True,
)


@prompts_app.command("show")
def prompts_show(
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """Show the active system prompt for an agent."""
    try:
        doc = get_prompt(
            agent_id,
            store=get_store(),
            project_root=get_settings().project_root,
            loader=get_loader(),
        )
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)
    except PromptError as exc:
        console.print(f"[red]{exc.code}: {exc.detail}[/red]")
        raise typer.Exit(1)

    if not doc.content:
        console.print("[yellow]No prompt content.[/yellow]")
        return

    console.print(
        Syntax(doc.content, "markdown", theme="ansi_dark", line_numbers=False)
    )


@prompts_app.command("edit")
def prompts_edit(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content: str = typer.Argument(..., help="New prompt content"),
) -> None:
    """Write a prompt to disk and create a new committed version."""
    try:
        put_prompt(
            agent_id,
            content,
            store=get_store(),
            project_root=get_settings().project_root,
            loader=get_loader(),
        )
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)
    except PromptError as exc:
        console.print(f"[red]{exc.code}: {exc.detail}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]updated[/green] agent {agent_id!r} prompt")


@prompts_app.command("versions")
def prompts_versions(
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """List prompt versions for an agent."""
    try:
        payload = list_versions(agent_id, store=get_store(), loader=get_loader())
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    committed = payload.get("committed", [])
    drafts = payload.get("drafts", [])

    if not committed and not drafts:
        console.print("[yellow]No prompt versions.[/yellow]")
        return

    if committed:
        table = Table(title="Committed", header_style="bold cyan")
        table.add_column("#", style="dim", justify="right")
        table.add_column("Author")
        table.add_column("Hash", style="dim")
        table.add_column("Created")
        for v in committed:
            table.add_row(
                str(v["version"]),
                v.get("author", ""),
                v.get("hash_", "")[:8],
                v.get("created_at", ""),
            )
        console.print(table)

    if drafts:
        table = Table(title="Drafts", header_style="bold yellow")
        table.add_column("#", style="dim", justify="right")
        table.add_column("Author")
        table.add_column("Updated")
        for v in drafts:
            table.add_row(
                str(v["version"]),
                v.get("author", ""),
                v.get("updated_at", ""),
            )
        console.print(table)


@prompts_app.command("show-version")
def prompts_show_version(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
) -> None:
    """Show a specific prompt version."""
    try:
        payload = get_version(
            agent_id, version, store=get_store(), loader=get_loader()
        )
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    if payload is None:
        console.print(f"[red]version {version} not found[/red]")
        raise typer.Exit(1)

    console.print(
        Syntax(payload.get("content", ""), "markdown", theme="ansi_dark")
    )
    console.print(
        f"[dim]v{payload.get('version')} — {payload.get('author', '')} "
        f"{payload.get('created_at', '')}[/dim]"
    )


@prompts_app.command("draft")
def prompts_draft(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content: str = typer.Argument(..., help="Draft content"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Save a draft prompt (not published until publish is called)."""
    try:
        save_draft(
            agent_id,
            content,
            store=get_store(),
            loader=get_loader(),
            author=author,
        )
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]saved draft[/green] for {agent_id!r}")


@prompts_app.command("publish")
def prompts_publish(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    changelog: str = typer.Option("", "--changelog", help="Publish reason"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Publish the current draft as the active prompt."""
    try:
        publish(
            agent_id,
            store=get_store(),
            project_root=get_settings().project_root,
            loader=get_loader(),
            changelog=changelog,
            author=author,
        )
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)
    except ValueError as exc:
        console.print(f"[red]no draft to publish: {exc}[/red]")
        raise typer.Exit(1)
    except PromptError as exc:
        console.print(f"[red]{exc.code}: {exc.detail}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]published[/green] {agent_id!r} prompt")


@prompts_app.command("rollback")
def prompts_rollback(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    target_version: int = typer.Argument(..., help="Version to roll back to"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Roll back to a previous prompt version."""
    try:
        rollback(
            agent_id,
            target_version,
            store=get_store(),
            project_root=get_settings().project_root,
            loader=get_loader(),
            author=author,
        )
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)
    except ValueError as exc:
        console.print(f"[red]rollback failed: {exc}[/red]")
        raise typer.Exit(1)
    except PromptError as exc:
        console.print(f"[red]{exc.code}: {exc.detail}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]rolled back[/green] to v{target_version} for {agent_id!r}")
