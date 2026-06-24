"""/api/api-tokens — per-environment encrypted secrets.

Plaintext is only returned at create/rotate time. Listing returns the
last four characters for identification. Secrets are Fernet-encrypted
at rest (key from ``AGENTBOX_SECRET_KEY`` env var or per-DB fallback).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentbox.core.service.system.service import SystemService

router = APIRouter(prefix="/api/api-tokens", tags=["api-tokens"])


class CreateBody(BaseModel):
    environment: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    secret: str = Field(..., min_length=4)


class RenameBody(BaseModel):
    name: str = Field(..., min_length=1)


class RotateBody(BaseModel):
    secret: str = Field(..., min_length=4)


def _svc() -> SystemService:
    return SystemService()


@router.get("")
def list_tokens(environment: str | None = None) -> dict:
    items = _svc().list_api_tokens(environment=environment)
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
def create_token(body: CreateBody) -> dict:
    try:
        return _svc().create_api_token(
            environment=body.environment, name=body.name, secret=body.secret
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(
                409, f"token ({body.environment!r}, {body.name!r}) already exists"
            ) from exc
        raise


@router.patch("/{token_id}")
def rename_token(token_id: str, body: RenameBody) -> dict:
    result = _svc().rename_api_token(token_id, body.name)
    if result is None:
        raise HTTPException(404, f"token {token_id!r} not found")
    return result


@router.post("/{token_id}/rotate")
def rotate_token(token_id: str, body: RotateBody) -> dict:
    try:
        result = _svc().rotate_api_token(token_id, secret=body.secret)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, f"token {token_id!r} not found")
    return result


@router.delete("/{token_id}", status_code=204)
def delete_token(token_id: str) -> None:
    if not _svc().delete_api_token(token_id):
        raise HTTPException(404, f"token {token_id!r} not found")
