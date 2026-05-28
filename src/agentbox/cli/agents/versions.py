"""agents versions — inspect and manage agent version history."""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli._deps import get_loader, get_store
from agentbox.cli._common import console
from agentbox.core.service import (
    add_version_comment,
    create_agent_version,
    diff_agent_versions,
    get_active_agent_version,
    get_agent_version,
    get_version_rating,
    latest_agent_version,
    list_agent_versions,
    list_version_comments,
    save_prompt_revision,
    set_version_rating,
)
from agentbox.core.service.agents import (
    AgentNotFound as ServiceAgentNotFound,
    require_agent_exists,
)

versions_app = typer.Typer(
    name="versions",
    help="Inspect agent version history.",
    no_args_is_help=True,
)


@versions_app.command("ls")
def versions_ls(
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """List all versions for an agent."""
    try:
        require_agent_exists(agent_id, store=get_store(), loader=get_loader())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    versions = list_agent_versions(store, agent_id)
    active = get_active_agent_version(store, agent_id)
    latest = latest_agent_version(store, agent_id)
    if active is None and latest is not None:
        active = latest
    active_id = active["id"] if active else None

    if not versions:
        console.print("[yellow]No versions.[/yellow]")
        return

    table = Table(title=f"Versions — {agent_id}", header_style="bold cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Author")
    table.add_column("Changelog")
    table.add_column("Draft", justify="center")
    table.add_column("Active", justify="center")
    table.add_column("Created")
    for v in versions:
        draft = "[yellow]✓[/yellow]" if v.get("is_draft") else "·"
        active_marker = "[green]✓[/green]" if v["id"] == active_id else "·"
        table.add_row(
            str(v["version"]),
            v.get("author", ""),
            v.get("changelog", "")[:60],
            draft,
            active_marker,
            v.get("created_at", ""),
        )
    console.print(table)
    console.print(
        f"[dim]latest: v{latest['version'] if latest else '-'}  "
        f"active: v{active['version'] if active else '-'}[/dim]"
    )


@versions_app.command("show")
def versions_show(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
) -> None:
    """Show full details for a specific version."""
    try:
        require_agent_exists(agent_id, store=get_store(), loader=get_loader())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    v = get_agent_version(store, agent_id, version)
    if v is None:
        console.print(f"[red]version {version} not found[/red]")
        raise typer.Exit(1)

    rating = get_version_rating(store, v["id"])
    comments = list_version_comments(store, v["id"])

    console.print(
        Panel(
            f"v{v['version']} — {v.get('author', '')} — {v.get('changelog', '')}",
            title=f"Version {version}",
        )
    )
    console.print(f"created: {v.get('created_at', '')}")
    if rating:
        console.print(f"rating: [yellow]{rating['rating']}/5[/yellow] by {rating.get('rater', '')}")

    if v.get("content_snapshot"):
        try:
            parsed = json.loads(v["content_snapshot"])
            console.print(
                Panel(
                    Syntax(
                        json.dumps(parsed, indent=2),
                        "json",
                        theme="ansi_dark",
                    ),
                    title="Content Snapshot",
                )
            )
        except json.JSONDecodeError:
            console.print(f"[dim]{v['content_snapshot'][:500]}[/dim]")

    if comments:
        ct = Table(header_style="bold cyan")
        ct.add_column("Author")
        ct.add_column("Body")
        ct.add_column("Created")
        for c in comments:
            ct.add_row(
                c.get("author", ""),
                c.get("body", "")[:80],
                c.get("created_at", ""),
            )
        console.print(Panel(ct, title="Comments"))


@versions_app.command("diff")
def versions_diff(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    a: int = typer.Argument(..., help="First version"),
    b: int = typer.Argument(..., help="Second version"),
) -> None:
    """Diff two agent versions."""
    try:
        require_agent_exists(agent_id, store=get_store(), loader=get_loader())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    try:
        result = diff_agent_versions(store, agent_id, a, b)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    console.print(
        Syntax(
            json.dumps(result, indent=2, default=str),
            "json",
            theme="ansi_dark",
        )
    )


@versions_app.command("comment")
def versions_comment(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    body: str = typer.Argument(..., help="Comment text"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Add a comment to a version."""
    try:
        require_agent_exists(agent_id, store=get_store(), loader=get_loader())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    v = get_agent_version(store, agent_id, version)
    if v is None:
        console.print(f"[red]version {version} not found[/red]")
        raise typer.Exit(1)

    result = add_version_comment(store, v["id"], author, body)
    console.print(f"[green]comment added[/green] (id={result['id']})")


@versions_app.command("rate")
def versions_rate(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    rating: int = typer.Argument(..., help="Rating (1-5)"),
    rater: str = typer.Option("cli", "--rater", help="Rater identifier"),
) -> None:
    """Rate a version (1-5)."""
    if not 1 <= rating <= 5:
        console.print("[red]rating must be 1-5[/red]")
        raise typer.Exit(2)

    try:
        require_agent_exists(agent_id, store=get_store(), loader=get_loader())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    v = get_agent_version(store, agent_id, version)
    if v is None:
        console.print(f"[red]version {version} not found[/red]")
        raise typer.Exit(1)

    try:
        set_version_rating(store, v["id"], rating, rater)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]rated[/green] v{version} → {rating}/5")


@versions_app.command("create")
def versions_create(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content_snapshot: str = typer.Argument(..., help="JSON content snapshot"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
    changelog: str = typer.Option("", "--changelog", help="Changelog"),
    prompt_snapshot: str = typer.Option("", "--prompt", help="Prompt snapshot"),
) -> None:
    """Create a new agent version from a snapshot."""
    loader = get_loader()
    agent = loader.get(agent_id)
    if agent is None:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    result = create_agent_version(
        store,
        agent_id=agent_id,
        source_path=str(agent.source_path) if agent.source_path else "",
        source_format=(
            agent.source_format.value if agent.source_format else "unknown"
        ),
        content_snapshot=content_snapshot,
        prompt_snapshot=prompt_snapshot,
        content_hash="",
        author=author,
        changelog=changelog,
    )
    console.print(f"[green]created[/green] v{result['version']} (id={result['id']})")


@versions_app.command("prompt-revision")
def versions_prompt_revision(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    prompt_content: str = typer.Argument(..., help="New prompt content"),
    changelog: str = typer.Option("", "--changelog", help="Changelog"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
    no_activate: bool = typer.Option(
        False, "--no-activate", help="Do not activate the new version"
    ),
) -> None:
    """Create a new agent version with edited prompt content."""
    try:
        require_agent_exists(agent_id, store=get_store(), loader=get_loader())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    try:
        result = save_prompt_revision(
            store,
            agent_id,
            prompt_content=prompt_content,
            author=author,
            changelog=changelog,
            activate=not no_activate,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]prompt revision[/green] v{result['version']} "
        f"(id={result['id']}, active={not no_activate})"
    )
