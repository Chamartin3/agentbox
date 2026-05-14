"""DB-only write endpoints under /api/agents (Plan 18).

These supersede the legacy ``/api/manifest/agents/*`` write endpoints.
The manifest routes 308-redirect here for one release.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core.data.manifest import AgentDef, AgentSource
from agentbox.core.definitions import ManifestWriter
from agentbox.core.services.agents import resolve_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# PATCH /api/agents/{id} — DB-first config save
# ---------------------------------------------------------------------------


class _RunnerPatch(BaseModel):
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


class _CompositionPatch(BaseModel):
    system: str | None = None
    user_template: str | None = None
    input_schema: str | None = None
    output_schema: str | None = None
    transport: str | None = None
    output_validation: str | None = None
    references: list[dict | str] | None = None


class _GuardrailPatch(BaseModel):
    name: str
    options: dict = Field(default_factory=dict)


class AgentPatch(BaseModel):
    """Editable subset of an AgentDef. All fields optional."""

    description: str | None = None
    session_mode: str | None = None
    workspace: str | None = None
    tags: list[str] | None = None
    tools: list[str] | None = None
    webhook_url: str | None = None
    headless: bool | None = None
    guardrails: list[_GuardrailPatch] | None = None
    runner: _RunnerPatch | None = None
    composition: _CompositionPatch | None = None


_FORBIDDEN_PATCH_KEYS = {"id"}


def _apply_patch_to_agent(agent_dump: dict, patch: dict) -> dict:
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


def _validate_runner_against_registry(agent: AgentDef) -> None:
    from agentbox.core.plugins import backend_load_failure, backends

    kind = agent.runner.kind
    name = kind.value if hasattr(kind, "value") else str(kind)
    loaded = backends()
    if name in loaded:
        return
    failure = backend_load_failure(name)
    if failure is not None:
        raise HTTPException(
            400,
            {
                "code": "backend_unloadable",
                "detail": (
                    f"runner.kind={name!r} is declared but failed to load "
                    f"at startup ({failure})."
                ),
            },
        )
    raise HTTPException(
        400,
        {
            "code": "backend_unknown",
            "detail": (
                f"runner.kind={name!r} has no backend installed. "
                f"Registered: {sorted(loaded.keys())}."
            ),
        },
    )


@router.patch("/{agent_id}")
def patch_agent(agent_id: str, body: AgentPatch) -> dict:
    """DB-first config save. Creates a new ``agent_versions`` row.

    On-disk files are not written by this endpoint — use
    ``POST /api/agents/{id}/export`` for that.
    """
    from agentbox.core.versioning.drift import _build_snapshot

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "empty patch")

    store = get_store()
    loader = get_loader()
    settings = get_settings()

    current = resolve_agent(agent_id, store=store, loader=loader)
    if current is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})

    merged = _apply_patch_to_agent(current.model_dump(mode="python"), patch)
    try:
        updated = AgentDef.model_validate(merged)
    except Exception as exc:
        raise HTTPException(
            400, {"code": "validation_failed", "detail": str(exc)}
        ) from exc
    _validate_runner_against_registry(updated)
    updated.source_path = current.source_path
    updated.source_format = current.source_format

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
            changelog=f"patch: {', '.join(sorted(patch))}",
            files=None,
        )
    except Exception as exc:
        logger.exception("patch_agent: DB write failed for %r", agent_id)
        raise HTTPException(
            500, {"code": "db_write_failed", "detail": agent_id}
        ) from exc

    store.upsert_agent_sync(
        agent_id=updated.id,
        proxy_path=str(updated.source_path) if updated.source_path else None,
    )

    return {"agent": updated.model_dump()}


# ---------------------------------------------------------------------------
# POST /api/agents/{id}/export — dump active version to disk
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    source_format: Literal["markdown", "standalone_toml", "legacy_dir"] = "markdown"
    target_path: str | None = None


class ExportResponse(BaseModel):
    source_path: str
    source_format: str
    written_files: list[str]


@router.post("/{agent_id}/export")
def export_agent(agent_id: str, body: ExportRequest) -> ExportResponse:
    """Serialize the active agent version to disk (one-way mirror)."""
    store = get_store()
    settings = get_settings()

    active = store.get_active_version(agent_id)
    if active is None:
        raise HTTPException(
            404, {"code": "unknown_agent", "detail": f"Agent {agent_id} not found"}
        )

    try:
        if active.get("config_json"):
            data = (
                json.loads(active["config_json"])
                if isinstance(active["config_json"], str)
                else active["config_json"]
            )
            agent_def = AgentDef.model_validate(data)
        else:
            agent_def = AgentDef.from_db_row(active)
    except Exception as exc:
        raise HTTPException(
            400, {"code": "agent_invalid", "detail": str(exc)}
        ) from exc

    if body.target_path:
        target_path = Path(body.target_path)
    else:
        agents_d = settings.project_root / "agents.d"
        if body.source_format == "legacy_dir":
            target_path = settings.project_root / "agents" / agent_id / "agent.toml"
        elif body.source_format == "standalone_toml":
            target_path = agents_d / f"{agent_id}.toml"
        else:
            target_path = agents_d / f"{agent_id}.md"

    agent_def.source_path = target_path
    agent_def.source_format = AgentSource(body.source_format)

    writer = ManifestWriter(settings.project_root)
    written_path = writer.save_agent(agent_def)

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


# ---------------------------------------------------------------------------
# POST /api/agents/import-file — opt-in legacy migration
# ---------------------------------------------------------------------------


class ImportRequest(BaseModel):
    """Opt-in file import for legacy migrations. Not the default workflow."""

    path: str
    source_format: Literal[
        "auto", "markdown", "standalone_toml", "legacy_dir", "inline_toml"
    ] = "auto"
    strategy: Literal["new_agent", "new_version", "skip", "overwrite"] = "new_agent"
    author: str = Field(..., min_length=1)
    changelog: str = Field(..., min_length=3)


class ImportResponse(BaseModel):
    agent_id: str
    version: int
    is_draft: bool
    skipped: bool = False


@router.post("/import-file")
def import_agent_from_file(body: ImportRequest):
    """Import an agent from disk into the DB. Migration helper only."""
    store = get_store()
    settings = get_settings()

    file_path = Path(body.path)
    if not file_path.exists():
        raise HTTPException(400, {"code": "file_not_found", "detail": body.path})

    inferred_format = body.source_format
    if inferred_format == "auto":
        if file_path.suffix == ".md":
            inferred_format = "markdown"
        elif file_path.suffix == ".toml":
            inferred_format = "standalone_toml"
        elif file_path.is_dir():
            inferred_format = "legacy_dir"
        else:
            inferred_format = "standalone_toml"

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
        else:
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

    _validate_runner_against_registry(agent_def)

    agent_id = agent_def.id
    existing = store.latest_version(agent_id)

    from agentbox.core.agent_config import build_config_json_payload

    config_dict = agent_def.model_dump(mode="python", exclude_none=False)
    if "source_path" in config_dict and isinstance(config_dict["source_path"], Path):
        config_dict["source_path"] = str(config_dict["source_path"])
    config_dict.update(build_config_json_payload(agent_def))
    config_json_str = json.dumps(config_dict, sort_keys=True, default=str)
    content_hash = hashlib.sha256(config_json_str.encode("utf-8")).hexdigest()

    try:
        prompt_content = agent_def.load_prompt(settings.project_root)
    except FileNotFoundError:
        prompt_content = agent_def.prompt or ""

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
        if body.strategy == "skip":
            return Response(
                content=json.dumps(
                    ImportResponse(
                        agent_id=agent_id,
                        version=existing.get("version", 0),
                        is_draft=bool(existing.get("is_draft", False)),
                        skipped=True,
                    ).model_dump()
                ),
                status_code=200,
                media_type="application/json",
            )
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
            content=json.dumps(
                ImportResponse(
                    agent_id=agent_id,
                    version=version_rec["version"],
                    is_draft=version_rec.get("is_draft", False),
                ).model_dump()
            ),
            status_code=201,
            media_type="application/json",
        )

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
        content=json.dumps(
            ImportResponse(
                agent_id=agent_id,
                version=version_rec["version"],
                is_draft=version_rec.get("is_draft", False),
            ).model_dump()
        ),
        status_code=201,
        media_type="application/json",
    )


# ---------------------------------------------------------------------------
# GET /api/agents/export-all — dump current TOML manifest
# ---------------------------------------------------------------------------


@router.get("/export-all")
def export_all() -> dict:
    """Return the current ``agentbox.toml`` text and parsed structure.

    Plan 18: this replaces ``GET /api/manifest`` (which is now an alias).
    The name reflects what the endpoint does: dump the live DB state
    expressed as TOML, for committing to git.
    """
    writer = ManifestWriter(get_settings().project_root)
    return {
        "path": str(writer.path),
        "text": writer.read_text(),
        "parsed": writer.read_parsed().model_dump(),
    }
