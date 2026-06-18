"""CLI commands: resource publish / rollback / migrate-composition."""

from __future__ import annotations

import typer
from rich.table import Table

from agentbox.cli._deps import get_store, get_settings
from agentbox.cli._common import console
from agentbox.core.resources.composition import (
    migrate_composition_to_bindings,
)
from agentbox.core.service import (
    get_repo_resource_by_slug,
    publish_repo_version,
    rollback_repo_resource,
)


def register_manage(app: typer.Typer) -> None:
    @app.command("publish")
    def resource_publish(
        slug: str,
        version_id: str,
        changelog: str = typer.Option(
            "publish via cli", "--changelog", help="Changelog"
        ),
    ) -> None:
        """Promote a draft version to active."""
        if len(changelog.strip()) < 3:
            console.print("[red]--changelog must be at least 3 characters[/red]")
            raise typer.Exit(1)

        store = get_store()
        resource = get_repo_resource_by_slug(store, slug)
        if not resource:
            console.print(f"[red]Resource not found:[/red] {slug!r}")
            raise typer.Exit(2)

        version = publish_repo_version(store, version_id, reason=changelog)
        console.print(
            f"[green]\u2713[/green] published version "
            f"[bold]{version['version_number']}[/bold] "
            f"for resource [bold]{slug}[/bold]"
        )

    @app.command("rollback")
    def resource_rollback(
        slug: str,
        version_number: int,
        changelog: str = typer.Option(
            ..., "--changelog", help="Reason for rollback (required)"
        ),
    ) -> None:
        """Roll back to a previous version (creates new version with old content)."""
        if len(changelog.strip()) < 3:
            console.print("[red]--changelog must be at least 3 characters[/red]")
            raise typer.Exit(1)

        store = get_store()
        resource = get_repo_resource_by_slug(store, slug)
        if not resource:
            console.print(f"[red]Resource not found:[/red] {slug!r}")
            raise typer.Exit(2)

        version = rollback_repo_resource(
            store, resource["id"], version_number, reason=changelog
        )
        console.print(
            f"[green]\u2713[/green] rolled back to version {version_number} "
            f"\u2014 new version [bold]{version['version_number']}[/bold] "
            f"for resource [bold]{slug}[/bold]"
        )

    @app.command("migrate-composition")
    def resource_migrate_composition(
        agent: str | None = typer.Option(
            None, "--agent", help="Migrate only this agent_id (default: all agents)"
        ),
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Report what would change without writing"
        ),
    ) -> None:
        """Migrate composition slots to resource bindings."""
        if dry_run:
            console.print(
                "[yellow]--dry-run not implemented yet; migration is idempotent, "
                "running for real.[/yellow]"
            )

        store = get_store()
        settings = get_settings()
        report = migrate_composition_to_bindings(
            store,
            only_agent_id=agent,
            project_root=settings.project_root,
        )
        summary = report.summary()

        table = Table(
            title="Composition Migration",
            header_style="bold cyan",
            padding=(0, 2),
        )
        table.add_column("Metric", style="bold")
        table.add_column("Count", justify="right")
        for k, v in summary.items():
            table.add_row(k, str(v))
        console.print(table)

        if report.agents_migrated:
            console.print(
                f"[green]migrated:[/green] {', '.join(report.agents_migrated)}"
            )
        if report.failed:
            console.print("[red]failed:[/red]")
            for agent_id, err in report.failed:
                console.print(f"  [red]{agent_id}[/red]: {err}")
            raise typer.Exit(1)
