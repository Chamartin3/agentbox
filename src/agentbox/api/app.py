"""FastAPI application factory.

Serves the React SPA at `/` from `ui/static/dist/` and the API at the
existing routes. Any unknown GET that doesn't match an API route returns
`index.html` so React Router can own client-side navigation.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from agentbox.api.routes import (
    activity,
    agents,
    health,
    manifest,
    mcp,
    prompts,
    runs,
    usage,
    versions,
    workspaces,
)
from agentbox.core.versioning.drift import startup_sweep

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
        _log.info("swept %d legacy .agentbox/generated/ directories under %s", swept, workspaces_root)


def _on_startup() -> None:
    """Initialize MCP connections and run drift sweep (best-effort, non-blocking)."""
    import agentbox.api.deps as _deps

    # Phase 0: warn if the manifest mount is absent (production should always bind-mount it).
    try:
        _deps.get_settings().check_manifest()
    except RuntimeError as exc:
        _log.critical("%s", exc)
        return

    # Phase 1: load manifest
    try:
        loader = _deps.get_loader()
        loaded_manifest = loader.load()
    except Exception:
        return

    # Phase 2: MCP (best-effort, non-blocking)
    try:
        if loaded_manifest.mcp_servers:
            registry = _deps.get_mcp_registry()
            specs = [s.model_dump() for s in loaded_manifest.mcp_servers]
            task = asyncio.ensure_future(registry.sync_servers(specs))
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    except Exception:
        pass

    # Phase 3: agent version drift sweep (best-effort, independent)
    try:
        store = _deps.get_store()
        startup_sweep(loaded_manifest.agents, store)
    except Exception:
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="agentbox", version="1.0.0", on_startup=[_on_startup])

    # API routers first.
    app.include_router(runs.router)
    app.include_router(agents.router)
    app.include_router(usage.router)
    app.include_router(workspaces.router)
    app.include_router(manifest.router)
    app.include_router(prompts.router)
    app.include_router(activity.router)
    app.include_router(mcp.router)
    app.include_router(health.router)
    app.include_router(versions.router)

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
