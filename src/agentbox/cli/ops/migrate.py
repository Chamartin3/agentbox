from __future__ import annotations

import json
import tomllib
from pathlib import Path

import typer
from rich.table import Table
from rich.text import Text

from agentbox.cli.shared import CliCtx
from agentbox.core.constants import BackendName
# TODO(cli-arch): SystemService.run_migration (core gap, plan 095)
from agentbox.core.db.system.seeds import backfill as _backfill_prompt_versions
# TODO(cli-arch): SystemService.run_migration (core gap, plan 095)
from agentbox.core.migrations import migrate_capabilities_to_manifest
from agentbox.core.service import (
    ProjectManifest,
    build_config_json_str,
    get_active_agent_version,
    get_agent_def,
    replace_version_config,
    update_agent_meta,
)

migrate_app = typer.Typer(
    name="migrate",
    help="Migrate configurations between versions.",
    no_args_is_help=True,
)


@migrate_app.command("ws-perms")
def migrate_ws_perms(ctx: typer.Context) -> None:
    """Migrate workspace permissions from capabilities.json to agentbox.toml.

    Reads each workspace's permissions/capabilities.json and patches the
    corresponding [[workspaces]] block in the manifest. Original JSON files
    are backed up with a timestamp.
    """
    obj: CliCtx = ctx.obj
    results = migrate_capabilities_to_manifest(obj.settings.project_root)

    if not results:
        obj.render.ops.warn("No workspaces found or no migration needed.")
        return

    table = Table(
        title="Workspace Permissions Migration",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Workspace", style="bold")
    table.add_column("Migrated", justify="center")
    table.add_column("Backup", justify="center")

    for ws_name, result in results.items():
        migrated = (
            Text("✓", style="green") if result["migrated"] else Text("·", style="dim")
        )
        backed_up = (
            Text("✓", style="green") if result["backed_up"] else Text("·", style="dim")
        )
        table.add_row(ws_name, migrated, backed_up)

    obj.render.ops.print(table)
    migrated_count = sum(1 for r in results.values() if r["migrated"])
    obj.render.ops.success(f"migrated [bold]{migrated_count}[/bold] workspace(s)")


@migrate_app.command("to-db-only")
def migrate_to_db_only(ctx: typer.Context, agent_id: str) -> None:
    """Migrate a TOML-backed agent to DB-only management.

    Reads the active version's source TOML, copies content into the DB
    if not already there, flips sync_mode to 'off' and export_to_disk to
    True so the file becomes an export mirror rather than the source of truth.

    Idempotent: running twice will not create duplicate versions.
    """
    obj: CliCtx = ctx.obj
    store = obj.store

    # Get active version
    active = get_active_agent_version(store, agent_id)
    if active is None:
        obj.render.ops.error(f"agent {agent_id!r} has no active version")
        raise typer.Exit(1)

    # If config_json is empty, load the agent and populate it
    if not active.get("config_json"):
        agent = get_agent_def(store, agent_id)
        if agent is None:
            obj.render.ops.error(f"could not load agent {agent_id!r} from DB")
            raise typer.Exit(1)

        # Rebuild the active version with config_json populated
        config_json_str = build_config_json_str(agent)
        replace_version_config(store, active["id"], config_json_str)
        obj.render.ops.info(f"populated config_json for v{active['version']}")

    # Update agent_meta: sync_mode="off", export_to_disk=True
    result = update_agent_meta(store, agent_id, sync_mode="off", export_to_disk=True)
    if result is None:
        obj.render.ops.error(f"agent_meta row not found for {agent_id!r}")
        raise typer.Exit(1)

    obj.render.ops.success(f"migrated {agent_id!r} to DB-only management")
    obj.render.ops.print("  sync_mode: watch → off")
    obj.render.ops.print(f"  export_to_disk: {bool(result.get('export_to_disk'))}")


@migrate_app.command("import-manifest")
def import_manifest(
    ctx: typer.Context,
    from_path: str | None = typer.Option(
        None, "--from", help="Path to agentbox.toml (defaults to project layout)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing settings when a key already exists."
    ),
) -> None:
    """Import project-level settings from ``agentbox.toml`` into the DB.

    Idempotent: keys already present in the DB are skipped unless
    ``--force`` is set. Run once per environment after upgrading; the
    on-disk manifest is no longer read at runtime.

    Imports:
    - ``[[mcp_servers]]`` → settings section ``project_mcp_servers``
    - ``[shared_assets]`` → settings section ``project_shared_assets``
    - ``backend_preference``/``tool_manifest_path``/``project`` →
      section ``project_runtime``
    """
    obj: CliCtx = ctx.obj
    settings = obj.settings

    if from_path:
        manifest_path = Path(from_path).expanduser()
    else:
        candidate_new = settings.project_root / "manifest.toml"
        candidate_old = settings.project_root / "agentbox.toml"
        manifest_path = candidate_new if candidate_new.exists() else candidate_old

    if not manifest_path.exists():
        obj.render.ops.warn(
            f"no manifest at {manifest_path}; nothing to import"
        )
        return

    with manifest_path.open("rb") as f:
        data = tomllib.load(f)
    manifest = ProjectManifest.model_validate(data)

    svc = obj.system

    existing_servers = svc.get_settings_section(obj.system.PROJ_MCP_SERVERS)
    existing_assets = svc.get_settings_section(obj.system.PROJ_SHARED_ASSETS)
    existing_runtime = svc.get_settings_section(obj.system.PROJ_RUNTIME)

    table = Table(
        title=f"Importing {manifest_path}",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Section")
    table.add_column("Key", style="bold")
    table.add_column("Action", justify="center")

    def _row(section: str, key: str, action: str, style: str) -> None:
        table.add_row(section, key, Text(action, style=style))

    for spec in manifest.mcp_servers or []:
        if not force and spec.name in existing_servers:
            _row(obj.system.PROJ_MCP_SERVERS, spec.name, "skip", "dim")
            continue
        svc.set_project_mcp_server(spec, author="migrate:import-manifest")
        _row(obj.system.PROJ_MCP_SERVERS, spec.name, "write", "green")

    for name, path in (manifest.shared_assets or {}).items():
        if not force and name in existing_assets:
            _row(obj.system.PROJ_SHARED_ASSETS, name, "skip", "dim")
            continue
        svc.set_project_shared_asset(name, path, author="migrate:import-manifest")
        _row(obj.system.PROJ_SHARED_ASSETS, name, "write", "green")

    runtime_writes: list[tuple[str, object]] = []
    if manifest.backend_preference:
        runtime_writes.append(("backend_preference", list(manifest.backend_preference)))
    if manifest.tool_manifest_path:
        runtime_writes.append(("tool_manifest_path", manifest.tool_manifest_path))
    if manifest.project and manifest.project != "default":
        runtime_writes.append(("project_name", manifest.project))

    for key, value in runtime_writes:
        if not force and key in existing_runtime:
            _row(obj.system.PROJ_RUNTIME, key, "skip", "dim")
            continue
        svc.set_setting(obj.system.PROJ_RUNTIME, key, value, author="migrate:import-manifest")
        _row(obj.system.PROJ_RUNTIME, key, "write", "green")

    obj.render.ops.print(table)
    obj.render.ops.print("done. manifest file may now be removed.")


@migrate_app.command("prompt-versions")
def migrate_prompt_versions(ctx: typer.Context) -> None:
    """Backfill ``runs.prompt_version_id`` from historical prompt_versions.

    See ``agentbox.core.db.backfill_prompt_versions``.
    """
    obj: CliCtx = ctx.obj
    n = _backfill_prompt_versions(obj.store)
    obj.render.ops.success(f"backfilled {n} run(s) with prompt_version_id")


@migrate_app.command("workenv-engine")
def migrate_workenv_engine(ctx: typer.Context) -> None:
    """Rename the old ``claude`` workenv-template engine to ``claude_code``.

    The recipe engine name now matches the backend entry-point name. Rows
    seeded before the rename still carry ``engine='claude'``; this updates
    them in place. Idempotent.
    """
    obj: CliCtx = ctx.obj
    store = obj.store
    renamed = 0
    for tmpl in store.list_workenv_templates():
        if tmpl.get("engine") == "claude":
            store.upsert_workenv_template(
                tmpl["name"],
                engine=BackendName.CLAUDE_CODE,
                config_json=json.loads(tmpl["config_json"])
                if isinstance(tmpl.get("config_json"), str)
                else tmpl.get("config_json", {}),
                description=tmpl.get("description"),
            )
            renamed += 1
    obj.render.ops.success(
        f"updated {renamed} template(s) "
        f"claude → {BackendName.CLAUDE_CODE}"
    )
