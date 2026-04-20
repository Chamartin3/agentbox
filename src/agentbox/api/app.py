"""FastAPI application factory.

Serves the React SPA at `/` from `ui/static/dist/` and the API at the
existing routes. Any unknown GET that doesn't match an API route returns
`index.html` so React Router can own client-side navigation.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from agentbox.api.routes import (
    activity,
    agents,
    manifest,
    mcp,
    prompts,
    runs,
    usage,
    workspaces,
)

SPA_DIR = Path(__file__).parent.parent / "ui" / "static" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="agentbox", version="0.1.0")

    # API routers first.
    app.include_router(runs.router)
    app.include_router(agents.router)
    app.include_router(usage.router)
    app.include_router(workspaces.router)
    app.include_router(manifest.router)
    app.include_router(prompts.router)
    app.include_router(activity.router)
    app.include_router(mcp.router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/health")
    def api_health() -> dict:
        return {"ok": True}

    # SPA assets.
    assets_dir = SPA_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_html = SPA_DIR / "index.html"

    @app.get("/{path:path}")
    def spa_fallback(path: str, request: Request) -> FileResponse:  # noqa: ARG001
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
