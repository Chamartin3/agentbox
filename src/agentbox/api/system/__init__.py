"""Platform/system API endpoints: health, settings, MCP, env-doc, host env."""

from __future__ import annotations

from fastapi import APIRouter

from . import credentials, env, health, host, mcp, project, settings

router = APIRouter()
router.include_router(health.router)
router.include_router(settings.router)
router.include_router(project.router)
router.include_router(host.router)
router.include_router(credentials.router)
router.include_router(mcp.router)
router.include_router(env.router)

__all__ = ["router"]
