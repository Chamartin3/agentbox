"""``agentbox versioning`` — bundle snapshot maintenance commands.

These tools exist for the DB-as-source-of-truth refactor: they backfill
existing ``agent_versions`` rows that predate ``agent_version_files`` and
let an operator pin a fresh version from the current disk bundle when
the DB has drifted from a known-good snapshot.
"""

from __future__ import annotations

import typer
from rich.table import Table

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.cli._common import console
from agentbox.core.versioning.bundle_capture import capture_bundle_files

versioning_app = typer.Typer(
    name="versioning",
    help="Bundle snapshot maintenance (backfill, publish-from-disk).",
    no_args_is_help=True,
)


def _shared_roots() -> dict:
    manifest = get_loader().load()
    project_root = get_settings().project_root
    return {
        k: (project_root / v).resolve()
        for k, v in (manifest.shared_assets or {}).items()
    }


@versioning_app.command("backfill-bundles")
def backfill_bundles(
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Single agent id; default = all agents."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without writing."
    ),
) -> None:
    """Snapshot bundle files into ``agent_version_files`` for existing versions.

    Walks each ``agent_versions`` row that has no files and tries to
    capture the bundle from disk using the row's current TOML. Rows
    whose source files are gone are listed and skipped.
    """
    store = get_store()
    loader = get_loader()
    project_root = get_settings().project_root
    shared_roots = _shared_roots()

    targets = [a for a in loader.load().agents if (agent is None or a.id == agent)]
    if not targets:
        console.print("[yellow]No matching agents.[/yellow]")
        raise typer.Exit(1)

    table = Table(title="Backfill result", header_style="bold cyan")
    table.add_column("Agent")
    table.add_column("Version")
    table.add_column("Files")
    table.add_column("Status")

    for ad in targets:
        try:
            rows = capture_bundle_files(ad, project_root, shared_roots)
        except Exception as exc:
            table.add_row(ad.id, "-", "0", f"[red]capture failed: {exc}[/red]")
            continue
        if not rows:
            table.add_row(ad.id, "-", "0", "[dim]no composition[/dim]")
            continue
        for v in store.list_versions(ad.id):
            existing = store.list_version_files(v["id"])
            if existing:
                table.add_row(
                    ad.id, str(v["version"]), str(len(existing)), "[dim]has files[/dim]"
                )
                continue
            if dry_run:
                table.add_row(
                    ad.id,
                    str(v["version"]),
                    str(len(rows)),
                    "[yellow]would backfill[/yellow]",
                )
            else:
                store.replace_version_files(v["id"], rows)
                table.add_row(
                    ad.id, str(v["version"]), str(len(rows)), "[green]backfilled[/green]"
                )
    console.print(table)


@versioning_app.command("publish-from-disk")
def publish_from_disk(
    agent_id: str = typer.Argument(..., metavar="AGENT_ID"),
    reason: str = typer.Option(
        ..., "--reason", "-r", help="Required changelog for the new version."
    ),
    activate: bool = typer.Option(
        True, "--activate/--no-activate", help="Promote the new version on success."
    ),
) -> None:
    """Capture the on-disk bundle and create a fresh ``agent_versions`` row.

    Use this when the DB version drifted from disk (e.g. someone edited
    the bundle directly) and you want to pin the current files as the
    authoritative snapshot.
    """
    if len(reason.strip()) < 3:
        console.print("[red]--reason must be at least 3 characters[/red]")
        raise typer.Exit(2)

    store = get_store()
    loader = get_loader()
    project_root = get_settings().project_root

    agent = loader.get(agent_id)
    if agent is None:
        console.print(f"[red]Unknown agent: {agent_id}[/red]")
        raise typer.Exit(1)

    files = capture_bundle_files(agent, project_root, _shared_roots())
    if not files:
        console.print(
            f"[yellow]Agent {agent_id!r} has no composition — nothing to capture.[/yellow]"
        )
        raise typer.Exit(1)

    import hashlib
    import json
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        config_json = json.dumps(
            agent.model_dump(mode="python", exclude={"prompt"}),
            sort_keys=True,
            default=str,
        )
        content_snapshot = json.dumps(
            agent.model_dump(mode="python"), sort_keys=True, default=str
        )

    prompt_text = ""
    sys_row = next((f for f in files if f["kind"] == "system"), None)
    if sys_row is not None:
        prompt_text = sys_row["content"]

    src = agent.source_path
    file_hash = (
        hashlib.sha256(src.read_bytes()).hexdigest()
        if src and src.exists() and src.is_file()
        else "unknown"
    )

    v = store.create_version(
        agent_id=agent.id,
        source_path=str(src) if src else "",
        source_format=(agent.source_format.value if agent.source_format else "unknown"),
        content_snapshot=content_snapshot,
        prompt_snapshot=prompt_text,
        content_hash=file_hash,
        author="cli:publish-from-disk",
        changelog=reason,
        config_json=config_json,
        prompt_content=prompt_text,
        source="manifest",
        is_draft=False,
        files=files,
    )
    if activate:
        store.activate_version(agent.id, v["id"])
    console.print(
        f"[green]Created v{v['version']} for {agent.id!r}[/green] "
        f"({len(files)} files{', activated' if activate else ''})"
    )
