"""CLI commands: resource upload."""

from __future__ import annotations

import contextlib
from pathlib import Path

import typer

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.service import (
    create_repo_resource,
    get_repo_resource_by_slug,
    import_repo_version,
)


def register_create(app: typer.Typer) -> None:
    @app.command("upload")
    def resource_upload(
        slug: str,
        file_path: str,
        changelog: str = typer.Option(
            "cli upload", "--changelog", help="Changelog for this version"
        ),
    ) -> None:
        """Upload a file as a new resource version (creates resource if absent)."""
        if len(changelog.strip()) < 3:
            console.print("[red]--changelog must be at least 3 characters[/red]")
            raise typer.Exit(1)

        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]File not found:[/red] {file_path}")
            raise typer.Exit(2)

        content = path.read_bytes()
        content_text: str | None = None
        with contextlib.suppress(UnicodeDecodeError):
            content_text = content.decode("utf-8")

        store = get_store()
        resource = get_repo_resource_by_slug(store, slug)
        if not resource:
            console.print(
                f"[yellow]Resource {slug!r} not found "
                f"\u2014 creating it as 'document'.[/yellow]"
            )
            resource = create_repo_resource(store, slug, "document", slug)

        version = import_repo_version(
            store,
            resource["id"],
            [("", content, None, content_text)],
            import_source="upload",
            changelog=changelog,
            activate=True,
        )
        console.print(
            f"[green]\u2713[/green] uploaded version "
            f"[bold]{version['version_number']}[/bold] "
            f"for resource [bold]{slug}[/bold] (id={version['id']})"
        )
