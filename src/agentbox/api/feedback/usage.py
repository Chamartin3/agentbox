"""/usage endpoints — aggregate token/cost rollups."""

from __future__ import annotations

from fastapi import APIRouter

from agentbox.core.service.evaluation.service import EvaluationService

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def aggregate() -> dict:
    return EvaluationService().aggregate_usage()
