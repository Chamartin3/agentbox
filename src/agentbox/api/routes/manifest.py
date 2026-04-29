"""/manifest endpoints — read the manifest, patch agent fields."""

from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core.definitions import ManifestWriter

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
    output_validation_engine: str | None = None
    max_validation_retries: int | None = None
    max_error_retries: int | None = None


class CompositionPatch(BaseModel):
    """Editable subset of a CompositionConfig. All fields optional."""

    system: str | None = None
    user_template: str | None = None
    input_schema: str | None = None
    output_schema: str | None = None
    transport: str | None = None
    output_validation: str | None = None
    references: list[dict | str] | None = None


class GuardrailPatch(BaseModel):
    name: str
    options: dict = Field(default_factory=dict)


class AgentPatch(BaseModel):
    """Editable subset of an AgentDef.

    All fields optional — only provided keys are applied.
    """

    description: str | None = None
    session_mode: str | None = None
    workspace: str | None = None
    tags: list[str] | None = None
    tools: list[str] | None = None
    webhook_url: str | None = None
    headless: bool | None = None
    guardrails: list[GuardrailPatch] | None = None
    runner: RunnerPatch | None = None
    composition: CompositionPatch | None = None


_FORBIDDEN_PATCH_KEYS = {"id"}


def _apply_patch_to_agent(agent_dump: dict, patch: dict) -> dict:
    """Merge ``patch`` into a model_dump of an AgentDef.

    Nested ``runner`` table merges per-field; everything else replaces.
    """
    out = dict(agent_dump)
    for k, v in patch.items():
        if k in _FORBIDDEN_PATCH_KEYS:
            continue
        if k == "runner" and isinstance(v, dict):
            base = dict(out.get("runner") or {})
            base.update({rk: rv for rk, rv in v.items() if rv is not None})
            out["runner"] = base
        elif k == "composition" and isinstance(v, dict):
            base = dict(out.get("composition") or {})
            base.update({ck: cv for ck, cv in v.items() if cv is not None})
            out["composition"] = base
        else:
            out[k] = v
    return out


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: str, body: AgentPatch) -> dict:
    """DB-first config save.

    Order of operations:
      1. Validate the patch against the in-memory ``AgentDef``.
      2. Create a new ``agent_versions`` row (DB is the source of truth).

    On-disk files are **not** updated by this endpoint.  A separate sync
    process (or manual export) can mirror the DB state to the filesystem
    when desired.
    """
    import hashlib
    import logging

    from agentbox.core.data.manifest import AgentDef
    from agentbox.core.versioning.drift import _build_snapshot, _capture_files_safe

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "empty patch")

    store = get_store()
    loader = get_loader()
    settings = get_settings()

    current = store.get_agent_def(agent_id) or loader.get(agent_id)
    if current is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})

    # --- step 1: build patched AgentDef and validate ---------------------
    merged = _apply_patch_to_agent(current.model_dump(mode="python"), patch)
    try:
        updated = AgentDef.model_validate(merged)
    except Exception as exc:
        raise HTTPException(
            400, {"code": "validation_failed", "detail": str(exc)}
        ) from exc
    # Preserve source metadata pydantic doesn't infer.
    updated.source_path = current.source_path
    updated.source_format = current.source_format

    # --- step 2: write DB ------------------------------------------------
    manifest = loader.load()
    shared_roots = {
        k: (settings.project_root / v).resolve()
        for k, v in (manifest.shared_assets or {}).items()
    }
    prompt_text = ""
    if updated.prompt_path:
        try:
            prompt_text = updated.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""
    files = _capture_files_safe(updated, settings.project_root, shared_roots)
    snapshot = _build_snapshot(updated)
    try:
        store.create_version(
            agent_id=updated.id,
            source_path=str(updated.source_path) if updated.source_path else "",
            source_format=(
                updated.source_format.value if updated.source_format else "unknown"
            ),
            content_snapshot=snapshot,
            prompt_snapshot=prompt_text,
            content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            author="api:patch",
            changelog=f"manifest patch: {', '.join(sorted(patch))}",
            files=files or None,
        )
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "manifest patch: DB write failed for %r", agent_id
        )
        raise HTTPException(
            500, {"code": "db_write_failed", "detail": agent_id}
        ) from exc

    # Track sync metadata so a separate sync process knows which file to mirror.
    store.upsert_agent_sync(
        agent_id=updated.id,
        proxy_path=str(updated.source_path) if updated.source_path else None,
    )

    return {"agent": updated.model_dump()}
