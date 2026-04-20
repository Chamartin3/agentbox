"""/usage endpoints — aggregate token/cost rollups."""

from __future__ import annotations

from fastapi import APIRouter

from agentbox.api.deps import get_store

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def aggregate() -> dict:
    return get_store().aggregate_usage()
