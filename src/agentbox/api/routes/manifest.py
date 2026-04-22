"""/manifest endpoints — read the manifest, patch agent fields."""

from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_settings
from agentbox.core.definitions import ManifestWriter, PatchError

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
    w = _writer()
    return {
        "path": str(w.path),
        "text": w.read_text(),
        "parsed": w.read_parsed().model_dump(),
    }


@router.get("/runner-models")
def list_runner_models(kind: str) -> dict:
    """Return available model identifiers for a runner kind."""
    if kind == "claude_code":
        return {"kind": kind, "models": _CLAUDE_MODELS}
    if kind == "opencode":
        return {"kind": kind, "models": _fetch_opencode_models()}
    return {"kind": kind, "models": []}


class RunnerPatch(BaseModel):
    """Editable subset of a RunnerSpec. All fields optional."""

    kind: str | None = None
    model: str | None = None
    mcp_config_path: str | None = None
    allowed_tools: list[str] | None = None
    extra_args: list[str] | None = None
    timeout_seconds: int | None = None
    agent_module: str | None = None
    output_schema_path: str | None = None
    max_validation_retries: int | None = None


class AgentPatch(BaseModel):
    """Editable subset of an AgentDef.

    All fields optional — only provided keys are applied.
    """

    description: str | None = None
    session_mode: str | None = None
    workspace: str | None = None
    tags: list[str] | None = None
    runner: RunnerPatch | None = None


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: str, body: AgentPatch) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "empty patch")
    try:
        updated = _writer().patch_agent(agent_id, patch)
    except PatchError as exc:
        status = {"unknown_agent": 404, "no_manifest": 404, "no_agents": 404}.get(
            exc.code, 400
        )
        raise HTTPException(status, {"code": exc.code, "detail": exc.detail}) from exc
    return {"agent": updated.model_dump()}
