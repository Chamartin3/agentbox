"""/usage endpoints — aggregate token/cost rollups."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def aggregate(ctx: APIContext = Depends(get_api_context)) -> dict:
    return ctx.evaluation.aggregate_usage()
