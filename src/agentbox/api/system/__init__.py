"""Platform/system API endpoints: health, settings, tokens, MCP, env-doc, host env."""

from __future__ import annotations

from fastapi import APIRouter

from . import env, health, host, mcp, project, settings, tokens

router = APIRouter()
router.include_router(health.router)
router.include_router(settings.router)
router.include_router(project.router)
router.include_router(host.router)
router.include_router(tokens.router)
router.include_router(mcp.router)
router.include_router(env.router)

__all__ = ["router"]
