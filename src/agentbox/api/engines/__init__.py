"""Runner-related API endpoints.

Aggregates the per-resource sub-routers (backends, profiles,
providers, aliases) under a single ``router`` that ``app.py`` includes.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import aliases, backends, profiles, providers

router = APIRouter()
router.include_router(backends.router)
router.include_router(profiles.router)
router.include_router(providers.router)
router.include_router(aliases.router)

__all__ = ["router"]
