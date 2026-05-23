"""Workspace-related API endpoints (CRUD + MCP overrides)."""

from __future__ import annotations

from fastapi import APIRouter

from . import crud, mcp

router = APIRouter()
router.include_router(crud.router)
router.include_router(mcp.router)

__all__ = ["router"]
