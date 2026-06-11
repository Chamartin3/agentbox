"""Analytics API endpoints: activity history, usage aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from . import activity, usage

router = APIRouter()
router.include_router(activity.router)
router.include_router(usage.router)

__all__ = ["router"]
