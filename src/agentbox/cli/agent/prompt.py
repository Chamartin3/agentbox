"""Agent prompts — show, edit, log, draft, publish, rollback."""

from __future__ import annotations

import typer
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli.shared import console, get_settings, get_store
from agentbox.core.service import get_prompt_version
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

prompt_app = typer.Typer(
    name="prompt",
    help="Manage system prompts: show, edit, log, draft, publish, rollback.",
    no_args_is_help=True,
)


@prompt_app.command("show")
def prompt_show(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int | None = typer.Option(
        None, "--version", help="Show a specific committed version"
    ),
) -> None:
    """Show the active system prompt for an agent (or a specific version)."""
    store = get_store()
    settings = get_settings()

    if version is not None:
        committed = get_prompt_version(store, agent_id, version)
        if committed is None:
            console.print(
                f"[red]version {version} not found for agent {agent_id!r}[/red]"
            )
            raise typer.Exit(2)
        content = committed["content"]
    else:
        try:
            doc = get_prompt(
                agent_id,
                store=store,
                project_root=settings.project_root,
            )
        except AgentNotFound:
            console.print(f"[red]unknown agent {agent_id!r}[/red]")
            raise typer.Exit(1)
        except PromptError as exc:
            console.print(f"[red]{exc.code}: {exc.detail}[/red]")
            raise typer.Exit(1)
        content = doc.content

    if not content:
        console.print("[yellow]No prompt content.[/yellow]")
        return

    console.print(
        Syntax(content, "markdown", theme="ansi_dark", line_numbers=False)
    )


@prompt_app.command("edit")
def prompt_edit(
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
        )
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)
    except PromptError as exc:
        console.print(f"[red]{exc.code}: {exc.detail}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]updated[/green] agent {agent_id!r} prompt")


@prompt_app.command("log")
def prompt_log(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int | None = typer.Option(
        None, "--version", help="Show a specific version's content"
    ),
) -> None:
    """List prompt versions, or show a specific version with --version."""
    try:
        payload = list_versions(agent_id, store=get_store())
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    committed = payload.get("committed", [])
    drafts = payload.get("drafts", [])

    if version is not None:
        ver = get_version(agent_id, version, store=get_store())
        if ver is None:
            console.print(f"[red]version {version} not found[/red]")
            raise typer.Exit(1)
        console.print(
            Syntax(ver.get("content", ""), "markdown", theme="ansi_dark")
        )
        console.print(
            f"[dim]v{ver.get('version')} -- {ver.get('author', '')} "
            f"{ver.get('created_at', '')}[/dim]"
        )
        return

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


@prompt_app.command("draft")
def prompt_draft(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content: str = typer.Argument(..., help="Draft content"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Save a draft prompt (not published until publish is called)."""
    try:
        save_draft(agent_id, content, store=get_store(), author=author)
    except AgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]saved draft[/green] for {agent_id!r}")


@prompt_app.command("publish")
def prompt_publish(
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


@prompt_app.command("rollback")
def prompt_rollback(
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
