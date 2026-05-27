"""CLI sub-app: agentbox env-doc — workspace env doc management."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.api.deps import get_store
from agentbox.cli._common import console

env_doc_app = typer.Typer(
    name="env-doc",
    help="Manage per-workspace environment documentation.",
    no_args_is_help=True,
)


def _load_content(content_or_file: str) -> dict:
    """Treat the arg as a file path first, then as raw JSON."""
    path = Path(content_or_file)
    text = path.read_text(encoding="utf-8") if path.exists() else content_or_file
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid JSON:[/red] {exc}")
        raise typer.Exit(2) from exc


@env_doc_app.command("show")
def env_doc_show(workspace_id: str) -> None:
    """Show the active env doc for a workspace."""
    store = get_store()
    doc = store.get_active_env_doc(workspace_id)
    if not doc:
        console.print(
            f"[yellow]No active env doc for workspace {workspace_id!r}.[/yellow]"
        )
        return

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("id", doc["id"])
    meta.add_row("version_number", str(doc["version_number"]))
    meta.add_row(
        "is_draft",
        "[yellow]draft[/yellow]" if doc.get("is_draft") else "[green]published[/green]",
    )
    meta.add_row("changelog", doc.get("changelog") or "—")
    meta.add_row("created_at", doc.get("created_at") or "—")
    console.print(Panel(meta, title=f"Env doc — {workspace_id}", border_style="cyan"))

    content = doc.get("content_json") or {}
    if isinstance(content, str):
        with contextlib.suppress(Exception):
            content = json.loads(content)
    console.print(
        Panel(
            Syntax(json.dumps(content, indent=2), "json", theme="ansi_dark"),
            title="Content",
            border_style="green",
        )
    )


@env_doc_app.command("versions")
def env_doc_versions(workspace_id: str) -> None:
    """List all env doc versions for a workspace."""
    store = get_store()
    rows = store.list_env_doc_versions(workspace_id)
    if not rows:
        console.print(
            f"[yellow]No env doc versions for workspace {workspace_id!r}.[/yellow]"
        )
        return

    table = Table(
        title=f"Env doc versions — {workspace_id}",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    table.add_column("Draft", justify="center")
    table.add_column("Changelog")
    table.add_column("Created at", style="dim")
    for v in rows:
        draft = (
            "[yellow]draft[/yellow]"
            if v.get("is_draft")
            else "[green]published[/green]"
        )
        table.add_row(
            str(v["version_number"]),
            v["id"],
            draft,
            v.get("changelog") or "",
            v.get("created_at") or "",
        )
    console.print(table)


@env_doc_app.command("edit")
def env_doc_edit(
    workspace_id: str,
    content_or_file: str,
    changelog: str = typer.Option(
        ..., "--changelog", help="Changelog (required, min 3 chars)"
    ),
) -> None:
    """Save a new env doc version (JSON content or path to a JSON file)."""
    if len(changelog.strip()) < 3:
        console.print("[red]--changelog must be at least 3 characters[/red]")
        raise typer.Exit(1)

    content = _load_content(content_or_file)
    store = get_store()
    doc = store.save_env_doc(workspace_id, content, changelog=changelog, publish=True)
    console.print(
        f"[green]✓[/green] env doc version [bold]{doc['version_number']}[/bold] saved "
        f"for workspace [bold]{workspace_id}[/bold]"
    )


@env_doc_app.command("publish")
def env_doc_publish(workspace_id: str, version_id: str) -> None:
    """Publish (activate) a specific env doc version."""
    store = get_store()
    doc = store.publish_env_doc(workspace_id, version_id)
    console.print(
        f"[green]✓[/green] env doc version [bold]{doc['version_number']}[/bold] published "
        f"for workspace [bold]{workspace_id}[/bold]"
    )


@env_doc_app.command("rollback")
def env_doc_rollback(
    workspace_id: str,
    version_id: str,
    changelog: str = typer.Option(
        ..., "--changelog", help="Reason for rollback (required, min 3 chars)"
    ),
) -> None:
    """Roll back to a previous env doc version (creates new version with old content)."""
    if len(changelog.strip()) < 3:
        console.print("[red]--changelog must be at least 3 characters[/red]")
        raise typer.Exit(1)

    store = get_store()
    doc = store.rollback_env_doc(workspace_id, version_id, changelog=changelog)
    console.print(
        f"[green]✓[/green] rolled back — new env doc version [bold]{doc['version_number']}[/bold] "
        f"for workspace [bold]{workspace_id}[/bold]"
    )
