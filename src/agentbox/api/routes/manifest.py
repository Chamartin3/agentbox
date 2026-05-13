"""/manifest endpoints — DEPRECATED compatibility shim (Plan 18).

All write paths now live under ``/api/agents/*``. The endpoints in this
module either redirect (308) or return ``deprecated: true`` alongside
their original response so legacy clients keep working for one release.

Removal target: see ``docs/plans/18-db-only-config-surface.md`` Phase 6.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from agentbox.api.deps import get_settings
from agentbox.core.definitions import ManifestWriter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manifest", tags=["manifest"])

_CLAUDE_MODELS = ["haiku", "sonnet", "opus"]
_opencode_models_cache: list[str] | None = None


def _fetch_opencode_models() -> list[str]:
    global _opencode_models_cache
    if _opencode_models_cache is not None:
        return _opencode_models_cache
    if shutil.which("opencode") is None:
        _opencode_models_cache = []
        return _opencode_models_cache
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    models = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and "/" in line
    ]
    _opencode_models_cache = models
    return models


def _writer() -> ManifestWriter:
    return ManifestWriter(get_settings().project_root)


@router.get("")
def get_manifest() -> dict:
    """DEPRECATED: use ``GET /api/agents/export-all``.

    Kept as an in-process alias (not a redirect) so legacy JSON clients
    continue working for one release.
    """
    w = _writer()
    return {
        "path": str(w.path),
        "text": w.read_text(),
        "parsed": w.read_parsed().model_dump(),
        "deprecated": True,
        "replacement": "/api/agents/export-all",
    }


@router.get("/runner-models")
def list_runner_models(kind: str) -> dict:
    """DEPRECATED: use ``/api/runner-providers/{provider}/models``."""
    if kind == "claude_code":
        models = _CLAUDE_MODELS
    elif kind == "opencode":
        models = _fetch_opencode_models()
    else:
        models = []
    return {
        "kind": kind,
        "models": models,
        "deprecated": True,
        "replacement": "/api/runner-providers/{provider}/models",
    }


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: str) -> RedirectResponse:
    """DEPRECATED: 308-redirects to ``PATCH /api/agents/{id}``."""
    return RedirectResponse(
        url=f"/api/agents/{agent_id}",
        status_code=308,
        headers={
            "Deprecation": "true",
            "Link": '</api/agents>; rel="successor-version"',
        },
    )


@router.post("/agents/{agent_id}/export")
def export_agent(agent_id: str) -> RedirectResponse:
    """DEPRECATED: 308-redirects to ``POST /api/agents/{id}/export``."""
    return RedirectResponse(
        url=f"/api/agents/{agent_id}/export",
        status_code=308,
        headers={"Deprecation": "true"},
    )


@router.post("/agents/import")
def import_agent() -> RedirectResponse:
    """DEPRECATED: 308-redirects to ``POST /api/agents/import-file``."""
    return RedirectResponse(
        url="/api/agents/import-file",
        status_code=308,
        headers={"Deprecation": "true"},
    )
