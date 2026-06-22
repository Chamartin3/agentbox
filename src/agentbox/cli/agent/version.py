"""Agent version — ls, show, new, note, publish, rollback."""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli.shared import console, handle_cli_errors, resolve_agent, get_store
from agentbox.core.service import (
    add_version_comment,
    branch_agent_draft,
    create_agent_version,
    diff_agent_versions,
    get_active_agent_version,
    get_agent_def,
    get_agent_version,
    get_version_rating,
    latest_agent_version,
    list_agent_versions,
    list_version_comments,
    publish_agent_version,
    rollback_agent_to,
    save_prompt_revision,
    set_version_rating,
)
from agentbox.core.service.agents import (
    AgentNotFound as ServiceAgentNotFound,
    require_agent_exists,
)

version_app = typer.Typer(
    name="version",
    help="Inspect and manage agent version history.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# ls
# ---------------------------------------------------------------------------


@version_app.command("ls")
def version_ls(
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """List all versions for an agent."""
    try:
        require_agent_exists(agent_id, store=get_store())
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
    table.add_column("Active", justify="center")
    table.add_column("Created")
    for v in versions:
        active_marker = "[green]✓[/green]" if v["id"] == active_id else "·"
        table.add_row(
            str(v["version"]),
            v.get("author", ""),
            v.get("changelog", "")[:60],
            active_marker,
            v.get("created_at", ""),
        )
    console.print(table)
    console.print(
        f"[dim]latest: v{latest['version'] if latest else '-'}  "
        f"active: v{active['version'] if active else '-'}[/dim]"
    )


# ---------------------------------------------------------------------------
# show  (two args → diff)
# ---------------------------------------------------------------------------


@version_app.command("show")
def version_show(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version_a: int = typer.Argument(..., help="Version number (or first version for diff)"),
    version_b: int | None = typer.Argument(None, help="Second version for diff"),
) -> None:
    """Show a version's details, or diff two versions when a second arg is given."""
    try:
        require_agent_exists(agent_id, store=get_store())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()

    # Diff path — two version arguments provided
    if version_b is not None:
        with handle_cli_errors():
            result = diff_agent_versions(store, agent_id, version_a, version_b)
        console.print(
            Syntax(json.dumps(result, indent=2, default=str), "json", theme="ansi_dark")
        )
        return

    # Single version detail
    v = get_agent_version(store, agent_id, version_a)
    if v is None:
        console.print(f"[red]version {version_a} not found[/red]")
        raise typer.Exit(1)

    rating = get_version_rating(store, v["id"])
    comments = list_version_comments(store, v["id"])

    console.print(
        Panel(
            f"v{v['version']} — {v.get('author', '')} — {v.get('changelog', '')}",
            title=f"Version {version_a}",
        )
    )
    console.print(f"created: {v.get('created_at', '')}")
    if rating:
        console.print(
            f"rating: [yellow]{rating['rating']}/5[/yellow] by {rating.get('rater', '')}"
        )

    if v.get("content_snapshot"):
        try:
            parsed = json.loads(v["content_snapshot"])
            console.print(
                Panel(
                    Syntax(json.dumps(parsed, indent=2), "json", theme="ansi_dark"),
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
            ct.add_row(c.get("author", ""), c.get("body", "")[:80], c.get("created_at", ""))
        console.print(Panel(ct, title="Comments"))


# ---------------------------------------------------------------------------
# new  (absorbs: create, prompt-revision, draft)
# ---------------------------------------------------------------------------


@version_app.command("new")
def version_new(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content_snapshot: str | None = typer.Argument(
        None, help="JSON content snapshot (direct create)"
    ),
    prompt: bool = typer.Option(
        False, "--prompt", help="Create version with new prompt content"
    ),
    prompt_content: str = typer.Option(
        "", "--content", help="New prompt content for --prompt"
    ),
    draft: bool = typer.Option(
        False, "--draft", help="Clone the active version as a new draft"
    ),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
    changelog: str = typer.Option("", "--changelog", help="Changelog"),
    no_activate: bool = typer.Option(
        False, "--no-activate", help="Do not activate the new version"
    ),
) -> None:
    """Create a new agent version.

    Three modes:

    \b
    1. Direct create: provide JSON ``content_snapshot`` (legacy).
       ``agent version new <agent> '{"..."}'``
    2. Prompt revision: ``--prompt --content "new prompt"``.
       ``agent version new <agent> --prompt --content "..."``
    3. Draft clone: ``--draft`` clones the active version.
       ``agent version new <agent> --draft``
    """
    store = get_store()

    if draft:
        # Clone active version as draft
        resolve_agent(agent_id)
        with handle_cli_errors():
            result = branch_agent_draft(store, agent_id, author=author)
        console.print(
            f"[green]draft created[/green] v{result.get('version')} "
            f"(id={result.get('id')})"
        )
        return

    if prompt:
        # Prompt revision
        try:
            require_agent_exists(agent_id, store=store)
        except ServiceAgentNotFound:
            console.print(f"[red]unknown agent {agent_id!r}[/red]")
            raise typer.Exit(1)
        with handle_cli_errors():
            result = save_prompt_revision(
                store, agent_id,
                prompt_content=prompt_content,
                author=author, changelog=changelog,
                activate=not no_activate,
            )
        console.print(
            f"[green]prompt revision[/green] v{result['version']} "
            f"(id={result['id']}, active={not no_activate})"
        )
        return

    # Direct create from snapshot
    if not content_snapshot:
        console.print(
            "[red]provide a JSON content_snapshot, or use --prompt or --draft[/red]"
        )
        raise typer.Exit(2)

    agent = get_agent_def(store, agent_id)
    if agent is None:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    result = create_agent_version(
        store,
        agent_id=agent_id,
        source_path=str(agent.source_path) if agent.source_path else "",
        source_format=(agent.source_format.value if agent.source_format else "unknown"),
        content_snapshot=content_snapshot,
        prompt_snapshot="",
        content_hash="",
        author=author,
        changelog=changelog,
    )
    console.print(f"[green]created[/green] v{result['version']} (id={result['id']})")


# ---------------------------------------------------------------------------
# note  (absorbs: comment + rate)
# ---------------------------------------------------------------------------


@version_app.command("note")
def version_note(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    comment: str | None = typer.Option(
        None, "--comment", help="Comment text to add"
    ),
    stars: int | None = typer.Option(
        None, "--stars", help="Rating 1-5"
    ),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Add a comment and/or star rating to a version."""
    if comment is None and stars is None:
        console.print("[red]pass --comment and/or --stars[/red]")
        raise typer.Exit(2)

    try:
        require_agent_exists(agent_id, store=get_store())
    except ServiceAgentNotFound:
        console.print(f"[red]unknown agent {agent_id!r}[/red]")
        raise typer.Exit(1)

    store = get_store()
    v = get_agent_version(store, agent_id, version)
    if v is None:
        console.print(f"[red]version {version} not found[/red]")
        raise typer.Exit(1)

    if comment is not None:
        result = add_version_comment(store, v["id"], author, comment)
        console.print(f"[green]comment added[/green] (id={result['id']})")

    if stars is not None:
        if not 1 <= stars <= 5:
            console.print("[red]rating must be 1-5[/red]")
            raise typer.Exit(2)
        with handle_cli_errors():
            set_version_rating(store, v["id"], stars, author)
        console.print(f"[green]rated[/green] v{version} → {stars}/5")


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


@version_app.command("publish")
def version_publish(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number to publish"),
    reason: str = typer.Option("cli publish", "--reason", help="Publish reason"),
) -> None:
    """Publish a draft version (set as active)."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = publish_agent_version(store, agent_id, version, reason)
    console.print(
        f"[green]published[/green] v{result.get('version')} "
        f"(id={result.get('id')})"
    )


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


@version_app.command("rollback")
def version_rollback(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Target version to roll back to"),
    reason: str = typer.Option(..., "--reason", help="Rollback reason (min 3 chars)"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Roll back to a previous agent version (creates a new version)."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = rollback_agent_to(store, agent_id, version, reason, author=author)
    console.print(
        f"[green]rolled back[/green] to v{version} (new v{result.get('version')})"
    )
