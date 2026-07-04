"""/usage endpoints — aggregate token/cost rollups."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.data.rows import UsageSummaryRow

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def aggregate(ctx: APIContext = Depends(get_api_context)) -> UsageSummaryRow:
    return ctx.evaluation.aggregate_usage()
