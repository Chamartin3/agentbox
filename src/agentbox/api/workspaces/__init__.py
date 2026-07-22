"""Workspace-related API endpoints (CRUD + MCP overrides + catalog)."""

from __future__ import annotations

from fastapi import APIRouter

from . import catalog, credentials, crud, mcp

router = APIRouter()
router.include_router(crud.router)
router.include_router(mcp.router)
router.include_router(catalog.router)
router.include_router(credentials.router)

__all__ = ["router"]
