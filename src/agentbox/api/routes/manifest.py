"""/manifest endpoints — legacy runner-model lookup only.

Plan 18 Phase 6: the agent write/import/export shims that used to live
here have been removed. The frontend and CLI talk to ``/api/agents/*``
directly. ``GET /api/manifest/runner-models`` is the last remaining
endpoint at this prefix and is on its own deprecation track (see the
``/api/runner-providers`` family).
"""

from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter

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
