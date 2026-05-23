"""DB-only write endpoints under /api/agents (Plan 18).

These supersede the legacy ``/api/manifest/agents/*`` write endpoints.
The manifest routes 308-redirect here for one release.
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_settings, get_store
from agentbox.core.data import AgentDef
from agentbox.core.service.agents import resolve_agent

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
    from agentbox.core.agent.plugins import backend_load_failure, backends

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
    import json as _json

    from agentbox.api.agents.validation import _decode_config_json
    from agentbox.core.prompt.versioning.drift import (
        _build_config_json,
        _build_snapshot,
    )

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "empty patch")

    store = get_store()
    settings = get_settings()

    current = resolve_agent(agent_id, store=store)
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
    config_json = _build_config_json(updated)

    # Carry forward prompt_content from the currently-active version so a
    # config-only PATCH never produces a row with NULL prompt_content (which
    # would crash the runtime with "agent X has no prompt source").
    active_row = store.get_active_version(agent_id)

    # Carry forward inline validators (config_json["input|output"]["validators"])
    # — AgentDef has no field for these, so _build_config_json drops them.
    # Without this merge, every PATCH silently clobbers the validators
    # written by PUT /api/agents/{id}/validation.
    prior_cfg = _decode_config_json((active_row or {}).get("config_json"))
    new_cfg = _json.loads(config_json)
    for direction in ("input", "output"):
        prior_section = prior_cfg.get(direction)
        if not isinstance(prior_section, dict) or "validators" not in prior_section:
            continue
        section = new_cfg.get(direction)
        if not isinstance(section, dict):
            section = {}
        section.setdefault("validators", prior_section["validators"])
        new_cfg[direction] = section
    config_json = _json.dumps(new_cfg)

    carried_prompt_content = (
        (active_row or {}).get("prompt_content") or prompt_text or None
    )
    carried_prompt_snapshot = (
        prompt_text or (active_row or {}).get("prompt_snapshot") or ""
    )

    try:
        new_version = store.create_version(
            agent_id=updated.id,
            source_path=str(updated.source_path) if updated.source_path else "",
            source_format=(
                updated.source_format.value if updated.source_format else "unknown"
            ),
            content_snapshot=snapshot,
            prompt_snapshot=carried_prompt_snapshot,
            content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            author="api:patch",
            changelog=f"patch: {', '.join(sorted(patch))}",
            files=None,
            config_json=config_json,
            prompt_content=carried_prompt_content,
        )
    except Exception as exc:
        logger.exception("patch_agent: DB write failed for %r", agent_id)
        raise HTTPException(
            500, {"code": "db_write_failed", "detail": agent_id}
        ) from exc

    # Activate the new version so subsequent reads (validation push,
    # runtime resolution, follow-up PATCHes) see this row instead of a
    # stale prior active. Skipping activation is what caused validation
    # push to overwrite freshly-PATCHed config (e.g. composition added
    # by a prior PATCH was clobbered because validation read the older
    # active row).
    try:
        store.activate_version(updated.id, int(new_version["id"]))
    except Exception as exc:
        logger.exception("patch_agent: activate_version failed for %r", agent_id)
        raise HTTPException(
            500, {"code": "activate_failed", "detail": agent_id}
        ) from exc

    store.upsert_agent_sync(
        agent_id=updated.id,
        proxy_path=str(updated.source_path) if updated.source_path else None,
    )

    return {"agent": updated.model_dump()}
