"""Validation-contract REST endpoints (Recovery plan Step 5).

Two surfaces:

1. ``/api/validation-contracts`` — CRUD on the reusable contract entity
   (``validation_contracts`` table). Same lifecycle as repo_resources:
   create once, edit in place, reference from many agent versions.

2. ``PUT /api/agents/{id}/validation`` — operates on the agent's active
   version. Body declares which contract applies to ``input`` and/or
   ``output`` for this version. The handler creates a NEW agent_version
   (cloning prompt/config/files from the active row), then writes the
   validation bindings against that new version. This matches the
   "editing validation creates a new version" rule from the recovery
   plan.

The schema (input/output structural shape) is NOT touched here — it
lives in ``agent_prompt_resource_bindings`` with ``slot='input_schema'``
or ``slot='output_schema'``. Keep these surfaces separate.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_settings, get_store
from agentbox.core.data.store import SessionStore
from agentbox.core.service.agents import resolve_agent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["validation-contracts"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class HttpValidatorIn(BaseModel):
    kind: Literal["http"] = "http"
    endpoint: str
    timeout_seconds: int = 5


class ScriptValidatorIn(BaseModel):
    kind: Literal["script"] = "script"
    resource_id: str
    pinned_version_id: str | None = None


ValidatorIn = HttpValidatorIn | ScriptValidatorIn


class ValidationContractCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    rules: list[str] = Field(default_factory=list)
    validators: list[dict] = Field(default_factory=list)
    actor: str | None = None


class ValidationContractPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    rules: list[str] | None = None
    validators: list[dict] | None = None


class InlineContract(BaseModel):
    """Anonymous one-off contract created on the fly by the validation PUT."""

    name: str | None = None
    description: str | None = None
    rules: list[str] = Field(default_factory=list)
    validators: list[dict] = Field(default_factory=list)


class DirectionBinding(BaseModel):
    contract_id: str | None = None
    inline: InlineContract | None = None


class AgentValidationPut(BaseModel):
    input: DirectionBinding | None = None
    output: DirectionBinding | None = None
    reason: str = Field(default="validation edit", min_length=1)
    actor: str | None = None


# ---------------------------------------------------------------------------
# Contract CRUD
# ---------------------------------------------------------------------------


def _enrich_contract(store: SessionStore, contract: dict) -> dict:
    refs = store.count_contract_references(contract["id"])
    return {**contract, "reference_count": refs}


@router.get("/api/validation-contracts")
def list_contracts(
    store: Annotated[SessionStore, Depends(get_store)],
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    items = store.list_validation_contracts(query=query, limit=limit, offset=offset)
    return {"items": [_enrich_contract(store, c) for c in items]}


@router.get("/api/validation-contracts/{contract_id}")
def get_contract(
    contract_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    contract = store.get_validation_contract(contract_id)
    if not contract:
        raise HTTPException(404, {"code": "contract_not_found", "detail": contract_id})
    return _enrich_contract(store, contract)


@router.post("/api/validation-contracts")
def create_contract(
    body: ValidationContractCreate,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        contract = store.create_validation_contract(
            name=body.name,
            description=body.description,
            rules=body.rules,
            validators=body.validators,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(400, {"code": "invalid_contract", "detail": str(exc)}) from exc
    return _enrich_contract(store, contract)


@router.patch("/api/validation-contracts/{contract_id}")
def update_contract(
    contract_id: str,
    body: ValidationContractPatch,
    store: Annotated[SessionStore, Depends(get_store)],
):
    patch = body.model_dump(exclude_unset=True)
    try:
        contract = store.update_validation_contract(contract_id, **patch)
    except ValueError as exc:
        raise HTTPException(400, {"code": "invalid_contract", "detail": str(exc)}) from exc
    return _enrich_contract(store, contract)


@router.delete("/api/validation-contracts/{contract_id}")
def delete_contract(
    contract_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    existing = store.get_validation_contract(contract_id)
    if not existing:
        raise HTTPException(404, {"code": "contract_not_found", "detail": contract_id})
    refs = store.count_contract_references(contract_id)
    if refs:
        raise HTTPException(
            409,
            {
                "code": "contract_in_use",
                "detail": f"contract {contract_id!r} is referenced by {refs} agent version(s)",
                "reference_count": refs,
            },
        )
    store.delete_validation_contract(contract_id)
    return {"deleted": contract_id}


# ---------------------------------------------------------------------------
# Per-agent validation binding
# ---------------------------------------------------------------------------


def _resolve_direction(
    store: SessionStore, direction: str, binding: DirectionBinding | None
) -> str | None:
    """Return the contract_id to bind for a direction, creating an anonymous
    inline contract if needed. Returns ``None`` to unbind."""
    if binding is None:
        return None
    if binding.contract_id and binding.inline:
        raise HTTPException(
            400,
            {
                "code": "ambiguous_binding",
                "detail": f"{direction}: provide either contract_id or inline, not both",
            },
        )
    if binding.contract_id:
        existing = store.get_validation_contract(binding.contract_id)
        if not existing:
            raise HTTPException(
                404,
                {
                    "code": "contract_not_found",
                    "detail": f"{direction}.contract_id={binding.contract_id!r}",
                },
            )
        return binding.contract_id
    if binding.inline:
        name = (binding.inline.name or "").strip()
        if not name:
            # Generate a stable-ish anonymous name. The contract itself is
            # still a first-class row — operators can rename it later via the
            # contracts CRUD page.
            import uuid

            name = f"inline:{direction}:{uuid.uuid4().hex[:8]}"
        try:
            created = store.create_validation_contract(
                name=name,
                description=binding.inline.description,
                rules=binding.inline.rules,
                validators=binding.inline.validators,
            )
        except ValueError as exc:
            raise HTTPException(
                400,
                {
                    "code": "invalid_inline_contract",
                    "detail": f"{direction}: {exc}",
                },
            ) from exc
        return created["id"]
    return None


@router.get("/api/agents/{agent_id}/validation")
def get_agent_validation(
    agent_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Return the active version's input/output contract bindings."""
    active = store.get_active_version(agent_id)
    if not active or active.get("id") is None:
        return {"agent_id": agent_id, "agent_version_id": None, "input": None, "output": None}
    version_id = int(active["id"])

    def _view(direction: str) -> dict | None:
        contract = store.resolve_agent_version_contract(version_id, direction)
        if not contract:
            return None
        return {
            "contract_id": contract["id"],
            "contract_name": contract["name"],
            "description": contract.get("description"),
            "rules": contract.get("rules") or [],
            "validators": contract.get("validators") or [],
        }

    return {
        "agent_id": agent_id,
        "agent_version_id": version_id,
        "input": _view("input"),
        "output": _view("output"),
    }


@router.put("/api/agents/{agent_id}/validation")
def put_agent_validation(
    agent_id: str,
    body: AgentValidationPut,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Bind validation contracts for the agent's input/output directions.

    Creates a NEW ``agent_versions`` row carrying the existing prompt and
    config, then activates it and writes the bindings against the new
    version. Per the recovery plan: editing validation bumps the version.
    Omitting a direction in the body leaves that direction unchanged on
    the new version (it's cloned forward by ``create_version``); passing
    ``null`` explicitly clears it.
    """
    settings = get_settings()
    current = resolve_agent(agent_id, store=store)
    if current is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})

    # Resolve target contract IDs BEFORE creating the new version so a
    # failure here doesn't leave a half-built version behind.
    explicit: dict[str, str | None] = {}
    if "input" in body.model_fields_set:
        explicit["input"] = _resolve_direction(store, "input", body.input)
    if "output" in body.model_fields_set:
        explicit["output"] = _resolve_direction(store, "output", body.output)

    if not explicit:
        raise HTTPException(
            400,
            {"code": "empty_validation_patch", "detail": "supply input and/or output"},
        )

    # Build a fresh version that carries everything forward. Re-use the
    # snapshot/config builders from the patch endpoint so this version
    # looks identical to a no-op PATCH save.
    from agentbox.core.prompt.versioning.drift import (
        _build_config_json,
        _build_snapshot,
    )

    prompt_text = ""
    if current.prompt_path:
        try:
            prompt_text = current.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""
    snapshot = _build_snapshot(current)
    config_json = _build_config_json(current)

    # Carry prompt_content forward — without this the validation PUT would
    # mint a new active version with an empty prompt, breaking subsequent
    # runs and previews. Prefer the inline prompt (live in config_json,
    # used by AgentDef.from_db_row), falling back to the legacy
    # prompt-file load above.
    carried_prompt_content = (current.prompt or "").strip() or prompt_text
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
            config_json=config_json,
            prompt_content=carried_prompt_content,
        )
    except Exception as exc:
        logger.exception("put_agent_validation: create_version failed for %r", agent_id)
        raise HTTPException(
            500, {"code": "db_write_failed", "detail": agent_id}
        ) from exc

    new_version_id = int(new_version["id"])

    # Activate the new version so downstream resolution picks it up
    # immediately (same behaviour as edit_prompt). Failure here would
    # leave the bindings on an inactive version — surface it.
    try:
        store.activate_version(current.id, new_version_id)
    except Exception as exc:
        logger.exception("put_agent_validation: activate_version failed for %r", agent_id)
        raise HTTPException(
            500, {"code": "activate_failed", "detail": agent_id}
        ) from exc

    # Apply the explicit bindings (overriding whatever clone_validation_bindings
    # copied forward from the previous active version).
    for direction, contract_id in explicit.items():
        try:
            store.set_agent_version_validation(
                new_version_id,
                direction=direction,
                contract_id=contract_id,
                actor=body.actor,
            )
        except ValueError as exc:
            raise HTTPException(
                400, {"code": "invalid_binding", "detail": str(exc)}
            ) from exc

    return get_agent_validation(agent_id, store)
