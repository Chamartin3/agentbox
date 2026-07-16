"""CLI sub-app: agentbox env-doc — workspace env doc management."""

from __future__ import annotations

import contextlib
import json as _json
from pathlib import Path

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.data.jsontypes import JsonDict


env_doc_app = typer.Typer(
    name="env-doc",
    help="Manage per-workspace environment documentation.",
    no_args_is_help=True,
)


def _load_content(content_or_file: str, obj: CLIContext) -> JsonDict:
    """Treat the arg as a file path first, then as raw JSON. Genuinely arbitrary JSON object."""
    path = Path(content_or_file)
    text = path.read_text(encoding="utf-8") if path.exists() else content_or_file
    try:
        return _json.loads(text)
    except _json.JSONDecodeError as exc:
        obj.render.system.env_doc_invalid_json(exc)
        raise typer.Exit(2) from exc


@env_doc_app.command("show")
def env_doc_show(ctx: typer.Context, workspace_id: str) -> None:
    """Show the active env doc for a workspace."""
    obj: CLIContext = ctx.obj
    doc = obj.workspaces.get_active_env_doc(workspace_id)
    if not doc:
        obj.render.system.env_doc_no_doc(workspace_id)
        return

    content = doc.get("content_json") or {}
    if isinstance(content, str):
        with contextlib.suppress(Exception):
            content = _json.loads(content)
    obj.render.system.env_doc_show_view(
        doc, workspace_id, _json.dumps(content, indent=2)
    )


@env_doc_app.command("versions")
def env_doc_versions(ctx: typer.Context, workspace_id: str) -> None:
    """List all env doc versions for a workspace."""
    obj: CLIContext = ctx.obj
    rows = obj.workspaces.list_env_doc_versions(workspace_id)
    obj.render.system.env_doc_versions_table(rows, workspace_id)


@env_doc_app.command("edit")
def env_doc_edit(
    ctx: typer.Context,
    workspace_id: str,
    content_or_file: str,
    changelog: str = typer.Option(
        ..., "--changelog", help="Changelog (required, min 3 chars)"
    ),
) -> None:
    """Save a new env doc version (JSON content or path to a JSON file)."""
    obj: CLIContext = ctx.obj
    if len(changelog.strip()) < 3:
        obj.render.system.env_doc_invalid_changelog()
        raise typer.Exit(1)

    content = _load_content(content_or_file, obj)
    doc = obj.workspaces.save_env_doc(workspace_id, content, changelog=changelog, publish=True)
    obj.render.system.env_doc_saved(doc["version_number"], workspace_id)


@env_doc_app.command("publish")
def env_doc_publish(ctx: typer.Context, workspace_id: str, version_id: str) -> None:
    """Publish (activate) a specific env doc version."""
    obj: CLIContext = ctx.obj
    doc = obj.workspaces.publish_env_doc(workspace_id, version_id)
    obj.render.system.env_doc_published(doc["version_number"], workspace_id)


@env_doc_app.command("rollback")
def env_doc_rollback(
    ctx: typer.Context,
    workspace_id: str,
    version_id: str,
    changelog: str = typer.Option(
        ..., "--changelog", help="Reason for rollback (required, min 3 chars)"
    ),
) -> None:
    """Roll back to a previous env doc version (creates new version with old content)."""
    obj: CLIContext = ctx.obj
    if len(changelog.strip()) < 3:
        obj.render.system.env_doc_invalid_changelog()
        raise typer.Exit(1)

    doc = obj.workspaces.rollback_env_doc(workspace_id, version_id, changelog=changelog)
    obj.render.system.env_doc_rolled_back(doc["version_number"], workspace_id)


@env_doc_app.command("preview")
def env_doc_preview(
    ctx: typer.Context,
    workspace_id: str = typer.Argument(..., help="Workspace ID"),
) -> None:
    """Preview env doc rendering for a workspace.

    Renders the active env doc for this workspace.
    """
    obj: CLIContext = ctx.obj
    doc = obj.workspaces.get_active_env_doc(workspace_id)
    if not doc:
        obj.render.system.env_doc_no_doc(workspace_id)
        return

    try:
        entries = obj.workspaces.render_env_doc(workspace_id, Path("."))
    except Exception as exc:
        obj.render.system.error(f"preview failed: {exc}")
        raise typer.Exit(1)

    obj.render.system.env_doc_preview(entries)
