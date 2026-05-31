"""FastAPI application factory.

Serves the React SPA at `/` from `ui/static/dist/` and the API at the
existing routes. Any unknown GET that doesn't match an API route returns
`index.html` so React Router can own client-side navigation.
"""

from __future__ import annotations

import logging
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
from agentbox.core import deps as _deps
from agentbox.core.service.lifecycle import run_startup_tasks

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
    """Run boot-time service-layer tasks.

    The disk manifest loader was removed in Plan 25; the DB is the
    source of truth, so the manifest is always ``None`` here.
    """
    settings = _deps.get_settings()
    store = _deps.get_store()
    report = run_startup_tasks(store, settings, manifest=None)
    if report.errors:
        _log.warning("startup completed with %d error(s)", len(report.errors))


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
