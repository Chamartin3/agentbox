"""/api/activity endpoints — KPIs, time series, breakdowns, recent runs."""

from __future__ import annotations

from fastapi import APIRouter, Query

from agentbox.api.deps import get_store
from agentbox.core.constants import ActivityStateFilter
from agentbox.core.service.execution.feedback import ActivityRange, enrich_recent_runs, summary

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("/summary")
def get_summary(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
) -> dict:
    return summary(get_store(), range_=range, agent=action)


@router.get("/runs")
def recent_runs(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
    state: ActivityStateFilter | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> dict:
    return enrich_recent_runs(
        get_store(),
        range_=range,
        agent=action,
        executor=executor,
        state=state,
        limit=limit,
    )
