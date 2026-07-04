"""/api/activity endpoints — KPIs, time series, breakdowns, recent runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from agentbox.api.context import APIContext
from agentbox.core.data.payload_types import EnrichedRunsResult
from agentbox.api.deps import get_api_context
from agentbox.core.data.constants import ActivityStateFilter
from agentbox.core.data.rows import ActivitySummaryRow
from agentbox.core.service.evaluation import ActivityRange, since_iso

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("/summary")
def get_summary(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
    ctx: APIContext = Depends(get_api_context),
) -> ActivitySummaryRow:
    return ctx.evaluation.activity_summary(since_iso(range), agent=action)


@router.get("/runs")
def recent_runs(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
    state: ActivityStateFilter | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    ctx: APIContext = Depends(get_api_context),
) -> EnrichedRunsResult:
    return ctx.evaluation.list_runs_enriched(
        range_=range,
        agent=action,
        executor=executor,
        state=state,
        limit=limit,
    )
