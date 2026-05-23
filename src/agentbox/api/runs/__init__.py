"""Run-related API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from . import crud

router = APIRouter()
router.include_router(crud.router)

__all__ = ["router"]
