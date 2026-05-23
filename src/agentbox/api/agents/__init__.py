"""Agent-related API endpoints.

Aggregates per-resource sub-routers under a single ``router``. Order
matters: ``io`` (export-all / import-file) and ``create`` must come
before ``crud`` because ``crud`` owns the ``/{agent_id}`` catch-all.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import create, crud, grants, io, prompts, tools, validation, versions

router = APIRouter()
# Specific paths first so /{agent_id} doesn't shadow them.
router.include_router(io.router)
router.include_router(create.router)
router.include_router(crud.router)
router.include_router(prompts.router)
router.include_router(versions.router)
router.include_router(validation.router)
router.include_router(grants.router)
router.include_router(tools.router)

__all__ = ["router"]
