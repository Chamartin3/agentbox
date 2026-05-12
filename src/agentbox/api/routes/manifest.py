"""/manifest endpoints — read the manifest, patch agent fields, export/import agents."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core.data.manifest import AgentDef, AgentSource
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
    w = _writer()
    return {
        "path": str(w.path),
        "text": w.read_text(),
        "parsed": w.read_parsed().model_dump(),
    }


@router.get("/runner-models")
def list_runner_models(kind: str) -> dict:
    """Return available model identifiers for a runner kind.

    DEPRECATED: Use /api/runner-providers/{provider_id}/models instead.

    This endpoint is deprecated in favor of the new provider-based model
    discovery API. See /api/runner-providers for available providers.
    """
    if kind == "claude_code":
        return {
            "kind": kind,
            "models": _CLAUDE_MODELS,
            "deprecated": True,
            "replacement": "/api/runner-providers/{provider}/models",
        }
    if kind == "opencode":
        return {
            "kind": kind,
            "models": _fetch_opencode_models(),
            "deprecated": True,
            "replacement": "/api/runner-providers/{provider}/models",
        }
    return {
        "kind": kind,
        "models": [],
        "deprecated": True,
        "replacement": "/api/runner-providers/{provider}/models",
    }


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
    from agentbox.core.versioning.drift import _build_snapshot

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
    prompt_text = ""
    if updated.prompt_path:
        try:
            prompt_text = updated.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""
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
            files=None,
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


# ------------------------------------------------------------------
# Export / Import
# ------------------------------------------------------------------


class ExportRequest(BaseModel):
    """Export an active agent version to disk."""

    source_format: Literal["markdown", "standalone_toml", "legacy_dir"] = "markdown"
    target_path: str | None = None


class ExportResponse(BaseModel):
    source_path: str
    source_format: str
    written_files: list[str]


@router.post("/agents/{agent_id}/export")
def export_agent(agent_id: str, body: ExportRequest) -> ExportResponse:
    """Serialize active agent version to disk.

    - Loads the active AgentDef from the DB.
    - Writes it via ManifestWriter to the specified format.
    - Updates agent_meta with the new source_path/source_format/export_to_disk=true.
    - Returns the written file path(s).
    """
    store = get_store()
    settings = get_settings()

    # Load active version
    active = store.get_active_version(agent_id)
    if active is None:
        raise HTTPException(
            404, {"code": "unknown_agent", "detail": f"Agent {agent_id} not found"}
        )

    # Reconstruct AgentDef from config_json or content_snapshot
    try:
        if active.get("config_json"):
            data = json.loads(active["config_json"]) if isinstance(active["config_json"], str) else active["config_json"]
            agent_def = AgentDef.model_validate(data)
        else:
            agent_def = AgentDef.from_db_row(active)
    except Exception as exc:
        raise HTTPException(
            400, {"code": "agent_invalid", "detail": str(exc)}
        ) from exc

    # Determine target path
    if body.target_path:
        target_path = Path(body.target_path)
    else:
        # Derive from source_format
        agents_d = settings.project_root / "agents.d"
        if body.source_format == "legacy_dir":
            target_path = settings.project_root / "agents" / agent_id / "agent.toml"
        elif body.source_format == "standalone_toml":
            target_path = agents_d / f"{agent_id}.toml"
        else:  # markdown
            target_path = agents_d / f"{agent_id}.md"

    # Stamp agent with source metadata
    agent_def.source_path = target_path
    agent_def.source_format = AgentSource(body.source_format)

    # Write via ManifestWriter
    writer = ManifestWriter(settings.project_root)
    written_path = writer.save_agent(agent_def)

    # Update agent_meta (or create if doesn't exist)
    meta = store.get_agent_meta(agent_id)
    if meta is None:
        store.init_agent_meta(
            agent_id,
            source_path=str(target_path),
            source_format=body.source_format,
            export_to_disk=True,
        )
    else:
        store.update_agent_meta(
            agent_id,
            source_path=str(target_path),
            source_format=body.source_format,
            export_to_disk=True,
        )

    return ExportResponse(
        source_path=str(target_path),
        source_format=body.source_format,
        written_files=[str(written_path)],
    )


class ImportRequest(BaseModel):
    """Import an agent from disk."""

    path: str
    source_format: Literal[
        "auto", "markdown", "standalone_toml", "legacy_dir", "inline_toml"
    ] = "auto"
    strategy: Literal["new_agent", "new_version", "skip", "overwrite"] = (
        "new_agent"
    )
    author: str = Field(..., min_length=1)
    changelog: str = Field(..., min_length=3)


class ConflictField(BaseModel):
    field: str
    db_value: str | None = None
    file_value: str | None = None


class ImportResponse(BaseModel):
    agent_id: str
    version: int
    is_draft: bool
    skipped: bool = False
    conflicts: list[ConflictField] = Field(default_factory=list)


@router.post("/agents/import")
def import_agent(body: ImportRequest):
    """Import an agent from disk, creating a DB version.

    Strategy handling:
    - new_agent: Create new agent if it doesn't exist; 409 if exists.
    - new_version: Create new version of existing agent.
    - skip: Return skipped=true if agent exists.
    - overwrite: Create new version and publish immediately.
    """
    store = get_store()
    settings = get_settings()

    file_path = Path(body.path)
    if not file_path.exists():
        raise HTTPException(400, {"code": "file_not_found", "detail": body.path})

    # Infer source_format if auto
    inferred_format = body.source_format
    if inferred_format == "auto":
        if file_path.suffix == ".md":
            inferred_format = "markdown"
        elif file_path.suffix == ".toml":
            inferred_format = "standalone_toml"
        elif file_path.is_dir():
            inferred_format = "legacy_dir"
        else:
            inferred_format = "standalone_toml"  # default

    # Parse the file using DefinitionLoader's logic
    agent_def = None
    try:
        if inferred_format == "markdown":
            from agentbox.core.definitions.markdown import load_markdown_agent

            agent_def = load_markdown_agent(file_path)
            if not isinstance(agent_def, AgentDef):
                agent_def = AgentDef.model_validate(agent_def)
        elif inferred_format == "legacy_dir":
            from agentbox.core.definitions.agents_dir import _load_legacy_dir_agent

            agent_def = _load_legacy_dir_agent(file_path, file_path.name)
            if not isinstance(agent_def, AgentDef):
                agent_def = AgentDef.model_validate(agent_def)
        else:  # standalone_toml or inline_toml
            import tomllib

            text = file_path.read_text(encoding="utf-8")
            data = tomllib.loads(text)
            agent_def = AgentDef.model_validate(data)
    except Exception as exc:
        raise HTTPException(
            400, {"code": "parse_error", "detail": str(exc)}
        ) from exc

    if agent_def is None:
        raise HTTPException(
            400, {"code": "parse_error", "detail": "Could not parse agent"}
        )

    agent_id = agent_def.id
    existing = store.latest_version(agent_id)

    # Build config dict for storage (convert Paths to strings)
    config_dict = agent_def.model_dump(mode="python", exclude_none=False)
    # Ensure Path objects are converted to strings
    if "source_path" in config_dict and isinstance(config_dict["source_path"], Path):
        config_dict["source_path"] = str(config_dict["source_path"])
    config_json_str = json.dumps(config_dict, sort_keys=True)
    content_hash = hashlib.sha256(config_json_str.encode("utf-8")).hexdigest()

    # Load prompt content if needed
    try:
        prompt_content = agent_def.load_prompt(settings.project_root)
    except FileNotFoundError:
        prompt_content = agent_def.prompt or ""

    # Handle strategy
    if existing is not None:
        if body.strategy == "new_agent":
            raise HTTPException(
                409,
                {
                    "code": "agent_exists",
                    "detail": f"Agent {agent_id} already exists",
                    "conflicts": [],
                },
            )
        elif body.strategy == "skip":
            return Response(
                content=json.dumps(ImportResponse(
                    agent_id=agent_id,
                    version=existing.get("version", 0),
                    is_draft=bool(existing.get("is_draft", False)),
                    skipped=True,
                ).model_dump()),
                status_code=200,
                media_type="application/json",
            )
        elif body.strategy in ("new_version", "overwrite"):
            # Create new version
            version_rec = store.create_version(
                agent_id=agent_id,
                source_path=str(file_path),
                source_format=inferred_format,
                content_snapshot="",
                prompt_snapshot=prompt_content or "",
                content_hash=content_hash,
                author=body.author,
                changelog=body.changelog,
                config_json=config_json_str,
                prompt_content=prompt_content,
                source="import",
                is_draft=(body.strategy == "new_version"),
            )

            if body.strategy == "overwrite":
                store.publish_version(agent_id, version_rec["version"], "imported")

            return Response(
                content=json.dumps(ImportResponse(
                    agent_id=agent_id,
                    version=version_rec["version"],
                    is_draft=version_rec.get("is_draft", False),
                ).model_dump()),
                status_code=201,
                media_type="application/json",
            )
    else:
        # New agent
        version_rec = store.create_agent(
            agent_id=agent_id,
            config_json=config_dict,
            prompt_content=prompt_content,
            author=body.author,
            changelog=body.changelog,
            source="import",
            source_path=str(file_path),
            source_format=inferred_format,
            export_to_disk=False,
        )

        return Response(
            content=json.dumps(ImportResponse(
                agent_id=agent_id,
                version=version_rec["version"],
                is_draft=version_rec.get("is_draft", False),
            ).model_dump()),
            status_code=201,
            media_type="application/json",
        )
