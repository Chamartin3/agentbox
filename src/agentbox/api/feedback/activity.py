"""/api/activity endpoints — KPIs, time series, breakdowns, recent runs."""

from __future__ import annotations

from fastapi import APIRouter, Query

from agentbox.core.constants import ActivityStateFilter
from agentbox.core.service.evaluation import ActivityRange, since_iso
from agentbox.core.service.evaluation.service import EvaluationService

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("/summary")
def get_summary(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
) -> dict:
    return EvaluationService().activity_summary(since_iso(range), agent=action)


@router.get("/runs")
def recent_runs(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
    state: ActivityStateFilter | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> dict:
    return EvaluationService().list_runs_enriched(
        range_=range,
        agent=action,
        executor=executor,
        state=state,
        limit=limit,
    )
