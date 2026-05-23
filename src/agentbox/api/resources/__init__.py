"""Resource-related API endpoints (shared repo + workspace bindings)."""

from __future__ import annotations

from fastapi import APIRouter

from . import bindings, crud, repo

router = APIRouter()
router.include_router(crud.router)
router.include_router(repo.router)
router.include_router(bindings.router)

__all__ = ["router"]
