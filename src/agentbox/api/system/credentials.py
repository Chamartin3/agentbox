"""/api/credentials — unified credential inventory + UI-managed store.

Read surface shows every credential the system knows about (files, env,
and UI-added), by source and state, **never values**. Writes add/overwrite
or delete UI-managed credentials. There is no reveal/extract endpoint:
secrets flow in and are materialized into runs, never returned to a caller.
"""

from __future__ import annotations

import re
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.data.rows import CredentialInventoryEntry, ManagedCredentialPublicRow

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


class InventoryResult(TypedDict):
    """Response envelope for GET /api/credentials."""

    items: list[CredentialInventoryEntry]
    total: int


class AddBody(BaseModel):
    # id is derived when omitted: env_var for api_key, else a slug of label.
    id: str | None = None
    label: str = Field(..., min_length=1)
    kind: str = Field(..., pattern="^(api_key|login)$")
    env_var: str | None = None
    secret: str = Field(..., min_length=1)


def _derive_id(body: AddBody) -> str:
    """Autogenerate a stable credential id from env_var or the label slug."""
    if body.id and body.id.strip():
        return body.id.strip()
    if body.kind == "api_key" and body.env_var:
        return body.env_var.strip()
    return re.sub(r"[^a-z0-9]+", "_", body.label.lower()).strip("_")


@router.get("")
def list_inventory(
    ctx: APIContext = Depends(get_api_context),
) -> InventoryResult:
    items = ctx.credentials.inventory()
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
def add_credential(
    body: AddBody,
    ctx: APIContext = Depends(get_api_context),
) -> ManagedCredentialPublicRow:
    credential_id = _derive_id(body)
    if not credential_id:
        raise HTTPException(400, "cannot derive credential id; provide env_var or a label")
    try:
        return ctx.credentials.add_credential(
            credential_id=credential_id,
            label=body.label,
            kind=body.kind,
            env_var=body.env_var,
            secret=body.secret,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{credential_id}", status_code=204)
def delete_credential(
    credential_id: str,
    ctx: APIContext = Depends(get_api_context),
) -> None:
    if not ctx.credentials.delete_credential(credential_id):
        raise HTTPException(404, f"credential {credential_id!r} not found")
