"""CLI commands: resource show / versions / preview-modes."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.service import (
    get_repo_resource_by_slug,
    import_repo_version,
    list_repo_versions,
)
from agentbox.core.service.bindings import preview_modes


def register_inspect(app: typer.Typer) -> None:
    @app.command("show")
    def resource_show(slug: str) -> None:
        """Show a resource and its version history."""
        store = get_store()
        resource = get_repo_resource_by_slug(store, slug)
        if not resource:
            console.print(f"[red]Resource not found:[/red] {slug!r}")
            raise typer.Exit(2)

        meta = Table.grid(padding=(0, 2))
        meta.add_column(style="dim", justify="right")
        meta.add_column()
        meta.add_row("id", resource["id"])
        meta.add_row("slug", resource["slug"])
        meta.add_row("type", resource["type"])
        meta.add_row("name", resource.get("display_name") or "\u2014")
        meta.add_row("description", resource.get("description") or "\u2014")
        meta.add_row("tags", resource.get("tags") or "\u2014")
        meta.add_row("status", resource.get("status") or "active")
        meta.add_row(
            "active_version_id", resource.get("active_version_id") or "\u2014"
        )
        console.print(
            Panel(meta, title=f"Resource: {slug}", border_style="cyan")
        )

        versions = list_repo_versions(store, resource["id"])
        if not versions:
            console.print("[dim]No versions.[/dim]")
            return

        vtable = Table(header_style="bold green", padding=(0, 1))
        vtable.add_column("#", style="dim")
        vtable.add_column("ID", style="dim")
        vtable.add_column("Draft", justify="center")
        vtable.add_column("Source")
        vtable.add_column("Changelog")
        vtable.add_column("Created at", style="dim")
        for v in versions:
            draft = (
                "[yellow]draft[/yellow]"
                if v.get("is_draft")
                else "[green]published[/green]"
            )
            vtable.add_row(
                str(v["version_number"]),
                v["id"],
                draft,
                v.get("import_source") or "",
                v.get("changelog") or "",
                v.get("created_at") or "",
            )
        console.print(Panel(vtable, title="Versions", border_style="green"))

    @app.command("versions")
    def resource_versions(
        slug: str = typer.Argument(..., help="Resource slug"),
        upload: bool = typer.Option(
            False, "--upload", help="Upload a new version from a file"
        ),
        file_path: str = typer.Option("", "--file", help="File path for --upload"),
        changelog: str = typer.Option(
            "cli upload", "--changelog", help="Changelog for uploaded version"
        ),
    ) -> None:
        """List or upload resource versions."""
        store = get_store()
        resource = get_repo_resource_by_slug(store, slug)
        if not resource:
            console.print(f"[red]Resource not found:[/red] {slug!r}")
            raise typer.Exit(2)

        if upload:
            if not file_path:
                console.print("[red]--file required for --upload[/red]")
                raise typer.Exit(2)
            path = Path(file_path)
            if not path.exists():
                console.print(f"[red]File not found:[/red] {file_path}")
                raise typer.Exit(2)
            content = path.read_bytes()
            content_text = None
            try:
                content_text = content.decode("utf-8")
            except UnicodeDecodeError:
                pass
            version = import_repo_version(
                store,
                resource["id"],
                [("", content, None, content_text)],
                import_source="upload",
                changelog=changelog,
                activate=True,
            )
            console.print(
                f"[green]uploaded[/green] version {version['version_number']} "
                f"(id={version['id']})"
            )
            return

        versions = list_repo_versions(store, resource["id"])
        if not versions:
            console.print("[dim]No versions.[/dim]")
            return

        vtable = Table(header_style="bold green", padding=(0, 1))
        vtable.add_column("#", style="dim")
        vtable.add_column("ID", style="dim")
        vtable.add_column("Draft", justify="center")
        vtable.add_column("Source")
        vtable.add_column("Changelog")
        vtable.add_column("Created at", style="dim")
        for v in versions:
            draft = (
                "[yellow]draft[/yellow]"
                if v.get("is_draft")
                else "[green]published[/green]"
            )
            vtable.add_row(
                str(v["version_number"]),
                v["id"],
                draft,
                v.get("import_source") or "",
                v.get("changelog") or "",
                v.get("created_at") or "",
            )
        console.print(vtable)

    @app.command("preview-modes")
    def resource_preview_modes(
        resource_id: str = typer.Argument(..., help="Resource ID"),
    ) -> None:
        """List available preview modes for a resource."""
        store = get_store()
        try:
            result = preview_modes(resource_id, store=store)
        except Exception:
            console.print(f"[red]resource {resource_id!r} not found[/red]")
            raise typer.Exit(1)
        modes = result.get("modes", [])
        if not modes:
            console.print(
                f"[dim]No preview modes for resource {resource_id!r}[/dim]"
            )
            return
        for m in modes:
            desc = (
                m.get("text", "")[:80]
                if m.get("text")
                else m.get("description", "")
            )
            console.print(f"[bold]{m.get('mode', '?')}[/bold]: {desc}")
