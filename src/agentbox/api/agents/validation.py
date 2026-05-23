"""Per-agent validation: inline ``config_json[direction].validators``
endpoints (Plan 23 Phase 3).

Two endpoints:

- ``GET  /api/agents/{id}/validation`` — read the active version's
  inline validators for both directions.
- ``PUT  /api/agents/{id}/validation`` — write inline validators by
  creating a NEW ``agent_versions`` row that carries everything
  forward (prompt, config, snapshot, files) and then mutating just
  ``config_json[direction].validators``. Activating that version
  makes the change live. Per the "editing validation bumps the
  version" rule the legacy contracts API enforced — preserved here.

The schema (input/output structural shape) is NOT touched here — it
lives in ``agent_prompt_resource_bindings`` with slot=``input_schema``
or ``output_schema``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_settings, get_store
from agentbox.core.data import SessionStore
from agentbox.core.service.agents import resolve_agent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-validation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class HttpValidatorIn(BaseModel):
    kind: Literal["http"] = "http"
    endpoint: str
    timeout_seconds: int = 5
    description: str = ""


class ScriptValidatorIn(BaseModel):
    kind: Literal["script"] = "script"
    resource_id: str
    pinned_version_id: str | None = None
    description: str = ""


ValidatorIn = HttpValidatorIn | ScriptValidatorIn

VALID_DIRECTIONS = ("input", "output")
VALID_KINDS = ("http", "script")


class DirectionBody(BaseModel):
    """Validators payload for a single direction. ``null`` clears the
    direction; an empty list also clears it (no validators); anything
    else replaces wholesale."""

    validators: list[dict] = Field(default_factory=list)


class AgentValidationPut(BaseModel):
    input: DirectionBody | None = None
    output: DirectionBody | None = None
    reason: str = Field(default="validation edit", min_length=1)
    actor: str | None = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_entries(direction: str, entries: list[dict]) -> list[dict]:
    """Return normalized validator entries or raise HTTPException(400)."""
    out: list[dict] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise HTTPException(
                400,
                {
                    "code": "invalid_validator",
                    "detail": f"{direction}.validators[{i}] must be an object",
                },
            )
        kind = entry.get("kind", "http")
        if kind not in VALID_KINDS:
            raise HTTPException(
                400,
                {
                    "code": "invalid_validator",
                    "detail": (
                        f"{direction}.validators[{i}].kind={kind!r} — must be "
                        f"one of {VALID_KINDS}. The jsonschema validator is "
                        "implicit from the schema binding and must not be "
                        "listed here."
                    ),
                },
            )
        desc = entry.get("description", "") or ""
        if not isinstance(desc, str):
            raise HTTPException(
                400,
                {
                    "code": "invalid_validator",
                    "detail": f"{direction}.validators[{i}].description must be a string",
                },
            )
        if kind == "http":
            endpoint = entry.get("endpoint")
            if not isinstance(endpoint, str) or not endpoint:
                raise HTTPException(
                    400,
                    {
                        "code": "invalid_validator",
                        "detail": f"{direction}.validators[{i}]: http requires a non-empty endpoint",
                    },
                )
            out.append(
                {
                    "kind": "http",
                    "endpoint": endpoint,
                    "timeout_seconds": int(entry.get("timeout_seconds", 5)),
                    "description": desc,
                }
            )
        else:  # script
            rid = entry.get("resource_id")
            if not isinstance(rid, str) or not rid:
                raise HTTPException(
                    400,
                    {
                        "code": "invalid_validator",
                        "detail": (
                            f"{direction}.validators[{i}]: script requires "
                            "resource_id (pointing at a repo_resource of type='script')"
                        ),
                    },
                )
            pinned = entry.get("pinned_version_id")
            if pinned is not None and not isinstance(pinned, str):
                raise HTTPException(
                    400,
                    {
                        "code": "invalid_validator",
                        "detail": (
                            f"{direction}.validators[{i}]: script.pinned_version_id "
                            "must be a string or null"
                        ),
                    },
                )
            row: dict = {"kind": "script", "resource_id": rid, "description": desc}
            if pinned:
                row["pinned_version_id"] = pinned
            out.append(row)
    return out


def _decode_config_json(raw: str | dict | None) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _direction_view(cfg: dict, direction: str) -> dict | None:
    section = cfg.get(direction)
    if not isinstance(section, dict):
        return None
    entries = section.get("validators")
    if not isinstance(entries, list) or not entries:
        return None
    cleaned: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        if kind not in VALID_KINDS:
            continue
        cleaned.append(dict(entry))
    if not cleaned:
        return None
    return {"validators": cleaned}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/agents/{agent_id}/validation")
def get_agent_validation(
    agent_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Return the active version's inline validators per direction."""
    active = store.get_active_version(agent_id)
    if not active or active.get("id") is None:
        return {
            "agent_id": agent_id,
            "agent_version_id": None,
            "input": None,
            "output": None,
        }
    cfg = _decode_config_json(active.get("config_json"))
    return {
        "agent_id": agent_id,
        "agent_version_id": int(active["id"]),
        "input": _direction_view(cfg, "input"),
        "output": _direction_view(cfg, "output"),
    }


@router.put("/api/agents/{agent_id}/validation")
def put_agent_validation(
    agent_id: str,
    body: AgentValidationPut,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Write inline validators by minting a new active version.

    Omitting a direction in the body leaves it unchanged on the new
    version (it's carried forward from the prior config_json).
    Passing ``{"validators": []}`` clears that direction.
    """
    settings = get_settings()
    current = resolve_agent(agent_id, store=store)
    if current is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})

    # Resolve target validator lists BEFORE writing so an invalid
    # payload doesn't leave a half-built version behind.
    explicit: dict[str, list[dict]] = {}
    if "input" in body.model_fields_set and body.input is not None:
        explicit["input"] = _validate_entries("input", body.input.validators)
    if "output" in body.model_fields_set and body.output is not None:
        explicit["output"] = _validate_entries("output", body.output.validators)
    if not explicit:
        raise HTTPException(
            400,
            {"code": "empty_validation_patch", "detail": "supply input and/or output"},
        )

    # Pull current config_json so unrelated keys (execution, runtime, …)
    # survive intact on the new version.
    active = store.get_active_version(current.id) or {}
    base_cfg = _decode_config_json(active.get("config_json"))
    for direction, validators in explicit.items():
        section = base_cfg.get(direction)
        if not isinstance(section, dict):
            section = {}
        section["validators"] = validators
        base_cfg[direction] = section
    new_config_json = json.dumps(base_cfg)

    # Build a fresh version that carries everything forward. Mirrors
    # the snapshot/config builders the prompt-patch endpoint uses so
    # the new version looks identical to a no-op PATCH save apart
    # from the validators delta.
    from agentbox.core.prompt.versioning.drift import _build_snapshot

    prompt_text = ""
    if current.prompt_path:
        try:
            prompt_text = current.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""
    snapshot = _build_snapshot(current)
    # Prefer the prompt_content already stored on the active version row
    # (the DB is the source of truth) — falling back to in-memory prompt and
    # then disk only for legacy/proxy agents where the active row is empty.
    carried_prompt_content = (
        active.get("prompt_content")
        or (current.prompt or "").strip()
        or prompt_text
        or None
    )

    try:
        new_version = store.create_version(
            agent_id=current.id,
            source_path=str(current.source_path) if current.source_path else "",
            source_format=(
                current.source_format.value if current.source_format else "unknown"
            ),
            content_snapshot=snapshot,
            prompt_snapshot=prompt_text,
            content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            author=body.actor or "api:validation",
            changelog=f"validation: {body.reason}",
            files=None,
            config_json=new_config_json,
            prompt_content=carried_prompt_content,
        )
    except Exception as exc:
        logger.exception("put_agent_validation: create_version failed for %r", agent_id)
        raise HTTPException(
            500, {"code": "db_write_failed", "detail": agent_id}
        ) from exc

    new_version_id = int(new_version["id"])
    try:
        store.activate_version(current.id, new_version_id)
    except Exception as exc:
        logger.exception(
            "put_agent_validation: activate_version failed for %r", agent_id
        )
        raise HTTPException(
            500, {"code": "activate_failed", "detail": agent_id}
        ) from exc

    return get_agent_validation(agent_id, store)
