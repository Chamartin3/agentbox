"""FastAPI application factory.

Serves the React SPA at `/` from `ui/static/dist/` and the API at the
existing routes. Any unknown GET that doesn't match an API route returns
`index.html` so React Router can own client-side navigation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from agentbox.api import (
    agents,
    analytics,
    resources,
    runners,
    runs,
    system,
    workspaces,
)
from agentbox.core.prompt.versioning.drift import startup_sweep
from agentbox.core.resource.boot_import import (
    import_composition_references,
    import_repo_resources,
    sweep_workspace_skill_bindings,
)
from agentbox.core.resource.composition_to_bindings import (
    migrate_composition_to_bindings,
)
from agentbox.core.resource.legacy_migration import (
    migrate_shared_resources_to_repo,
)

SPA_DIR = Path(__file__).parent.parent / "ui" / "static" / "dist"


_log = logging.getLogger(__name__)


def _sweep_legacy_generated(workspaces_root: Path) -> None:
    """Delete any leftover .agentbox/generated/ trees under every workspace.

    Generated configs are now written to per-run tmpfs dirs; these directories
    are always derived content and safe to delete on startup.
    """
    if not workspaces_root.is_dir():
        return
    swept = 0
    for ws in workspaces_root.iterdir():
        legacy = ws / ".agentbox" / "generated"
        if legacy.is_dir():
            shutil.rmtree(legacy, ignore_errors=True)
            swept += 1
    if swept:
        _log.info(
            "swept %d legacy .agentbox/generated/ directories under %s",
            swept,
            workspaces_root,
        )


def _on_startup() -> None:
    """Initialize MCP connections and run drift sweep (best-effort, non-blocking).

    Manifest-free startup: works when either a manifest exists OR the DB has
    agents. Operators can bootstrap with just the DB and create agents via API.
    """
    import agentbox.api.deps as _deps

    settings = _deps.get_settings()
    store = _deps.get_store()

    # Populate the shared agent_tools registry from installed entry points so
    # /api/agent_tools and the control-plane MCP can list discovered tools.
    try:
        from agentbox.core.tools.discovery import discover_tools

        discover_tools()
    except Exception:
        _log.exception("agent_tools discovery failed")

    # Phase 0: check runtime sources (manifest-free startup support)
    # Always returns True; no longer raises on missing manifest.
    settings.check_runtime_sources(store)

    # Phase 1: load manifest (if it exists)
    loaded_manifest = None
    try:
        loader = _deps.get_loader()
        loaded_manifest = loader.load()
        if settings.manifest_path.exists():
            _log.debug("manifest loaded successfully")
        else:
            _log.info("manifest not found; running in manifest-free mode")
    except Exception as exc:
        _log.warning("manifest load failed: %s; continuing anyway", exc)

    # Phase 2: MCP (best-effort, non-blocking)
    project_mcp_servers = store.get_project_mcp_servers()
    if project_mcp_servers:
        try:
            registry = _deps.get_mcp_registry()
            specs = [s.model_dump() for s in project_mcp_servers]
            task = asyncio.ensure_future(registry.sync_servers(specs))
            task.add_done_callback(
                lambda t: t.exception() if not t.cancelled() else None
            )
        except Exception:
            pass

    # Phase 3: agent version drift sweep.
    #
    # Plan 18: filesystem → DB import is opt-in. Without
    # ``AGENTBOX_IMPORT_ON_START=1`` the manifest is read-only at boot and
    # files can never silently overwrite DB state. Operators migrating an
    # existing install can flip the flag once, then turn it back off.
    if (
        loaded_manifest
        and loaded_manifest.agents
        and os.environ.get("AGENTBOX_IMPORT_ON_START") == "1"
    ):
        try:
            _project_root = settings.project_root
            _shared_roots = {
                k: (_project_root / v).resolve()
                for k, v in store.get_project_shared_assets().items()
            }
            startup_sweep(
                loaded_manifest.agents,
                store,
                project_root=_project_root,
                shared_roots=_shared_roots,
            )
        except Exception:
            pass

    # Phase 3b: seed default runner profiles (idempotent).
    # Set AGENTBOX_SKIP_DEFAULT_PROFILES=1 to opt out (used by the test suite).
    if not os.environ.get("AGENTBOX_SKIP_DEFAULT_PROFILES"):
        try:
            from agentbox.core.data import (seed_default_runner_profiles,
            )

            created = seed_default_runner_profiles(store)
            if created:
                _log.info("seeded %d default runner profile(s)", created)
        except Exception:
            _log.exception("default runner profile seed failed")

    # Phase 3c: populate the central resource repository from the on-disk
    # manifest layout (Plan 01 §Migration + Plan 03 §Migration). Imports
    # skills/schemas/prompts/shared-folders into repo_resources and wires
    # manifest-declared workspace skills as workspace_file_resource_bindings.
    # Set AGENTBOX_SKIP_RESOURCE_IMPORT=1 to opt out.
    if not os.environ.get("AGENTBOX_SKIP_RESOURCE_IMPORT"):
        try:
            summary = import_repo_resources(store, settings.project_root)
            if summary["created"] or summary["updated"]:
                _log.info(
                    "boot-import repo_resources: created=%d updated=%d skipped=%d failed=%d",
                    summary["created"],
                    summary["updated"],
                    summary["skipped"],
                    summary["failed"],
                )
            # Plan 01 legacy sweep: move shared_resources rows into the
            # unified repo. Runs after import_repo_resources so that
            # manifest-imported rows take precedence and overlapping legacy
            # rows are skipped by slug match. Idempotent.
            try:
                legacy_report = migrate_shared_resources_to_repo(store)
                _summary = legacy_report.summary()
                if _summary["migrated"] or _summary["failed"]:
                    _log.info(
                        "legacy shared_resources sweep: %s",
                        _summary,
                    )
                else:
                    _log.debug("legacy shared_resources sweep: %s", _summary)
            except Exception:
                _log.exception("legacy shared_resources sweep failed")

            ws_summary = sweep_workspace_skill_bindings(store, loaded_manifest)
            if ws_summary["bindings_added"]:
                _log.info(
                    "boot-import workspace bindings: wired %d workspace(s), %d binding(s)",
                    ws_summary["workspaces_wired"],
                    ws_summary["bindings_added"],
                )

            ref_summary = import_composition_references(
                store,
                settings.project_root,
                loaded_manifest,
            )
            if ref_summary["bindings_added"]:
                _log.info(
                    "boot-import composition refs: wired %d agent(s), %d resource(s), %d binding(s)",
                    ref_summary["agents_wired"],
                    ref_summary["resources_created"],
                    ref_summary["bindings_added"],
                )

            # Phase 3d: migrate composition slots (input_schema, output_schema,
            # user_template) into resource_bindings. Gated for first rollout.
            if os.environ.get("AGENTBOX_MIGRATE_COMPOSITION"):
                try:
                    comp_report = migrate_composition_to_bindings(
                        store,
                        project_root=settings.project_root,
                    )
                    _comp_summary = comp_report.summary()
                    if _comp_summary["bindings_created"] or _comp_summary["failed"]:
                        _log.info(
                            "composition→bindings migration: %s",
                            _comp_summary,
                        )
                    else:
                        _log.debug(
                            "composition→bindings migration: %s",
                            _comp_summary,
                        )
                except Exception:
                    _log.exception("composition→bindings migration failed")
        except Exception:
            _log.exception("repo-resource boot import failed")

    # Phase 3e: sync canonical workspaces registry. The migration already
    # backfilled from satellite tables once. That was too greedy — any
    # workspace_id ever written by experimental code (empty dirs, one-off
    # MCP overrides) became a permanent phantom row. Going forward:
    #
    #   1. No more auto-backfill from satellites. Registry rows are
    #      created explicitly: by manifest sync, by POST /api/workspaces,
    #      or by the executor when a real run needs a new workspace.
    #   2. Upsert manifest workspaces with source='manifest'.
    #   3. Prune phantoms — auto-backfilled rows that aren't in the
    #      manifest, have no agent referencing them, and have no rows in
    #      any satellite table. On-disk dirs are left alone.
    try:
        keep_names: set[str] = {"default"}
        if loaded_manifest:
            keep_names |= {a.workspace or "default" for a in loaded_manifest.agents}
        pruned = store.prune_phantom_workspaces(keep=keep_names)
        if pruned:
            _log.info(
                "pruned %d phantom workspace registry rows: %s",
                len(pruned),
                sorted(pruned),
            )
    except Exception:
        _log.exception("workspaces registry sync failed")

    # Phase 4: reap orphaned 'running' rows from a previous process.
    try:
        reaped = store.reap_orphan_runs()
        if reaped:
            _log.warning("reaped %d orphaned 'running' run(s) on startup", reaped)
    except Exception:
        _log.exception("orphan run sweep failed")

    # Phase 5: fire webhooks for orphan-reaped runs whose post pipeline
    # never ran. SessionStore._init reaps orphans synchronously at
    # construction time, before the event loop exists — so schedule_webhook
    # couldn't have fired then. We do it here, once the loop is up.
    #
    # Agents are resolved via ``resolve_agent`` (DB first, manifest fallback)
    # so DB-only agents and agents missing from the in-memory manifest still
    # get their completion webhooks delivered.
    try:
        from agentbox.api.webhooks import schedule_webhook
        from agentbox.core.service.agents import resolve_agent

        loader = _deps.get_loader()
        pending = store.list_orphaned_unnotified_runs()
        if pending:
            _log.warning(
                "scheduling webhooks for %d orphan-reaped run(s)", len(pending)
            )
        for run in pending:
            agent = resolve_agent(run.agent_id, store=store, loader=loader)
            schedule_webhook(agent, run, store)
    except Exception:
        _log.exception("orphan webhook dispatch failed")


def create_app() -> FastAPI:
    app = FastAPI(title="agentbox", version="1.0.0", on_startup=[_on_startup])

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # FastAPI's default 500 returns `Internal Server Error` text — clients
        # then have to crack open server logs to see what went wrong. Render a
        # JSON envelope with the exception type + message so consumers (and
        # the UI) can surface the real cause directly.
        _log.exception("unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"{type(exc).__name__}: {exc}",
                "error": str(exc) or type(exc).__name__,
                "path": request.url.path,
            },
        )

    # Resource-grouped routers — each subpackage's __init__.py owns the
    # include order of its children.
    app.include_router(runs.router)
    app.include_router(agents.router)
    app.include_router(workspaces.router)
    app.include_router(resources.router)
    app.include_router(runners.router)
    app.include_router(analytics.router)
    app.include_router(system.router)

    # SPA assets.
    assets_dir = SPA_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_html = SPA_DIR / "index.html"

    @app.get("/{path:path}")
    def spa_fallback(path: str, request: Request) -> FileResponse:
        if not index_html.exists():
            return JSONResponse(
                {
                    "error": "SPA bundle not built",
                    "hint": "run `npm run build` in libs/agentbox/web/",
                },
                status_code=503,
            )
        # API endpoints live under /api/ — never serve the SPA for those.
        first = path.split("/", 1)[0]
        if first in {"api", "assets", "health"}:
            raise HTTPException(404)
        return FileResponse(index_html)

    return app


app = create_app()
