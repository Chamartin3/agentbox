"""Pydantic models used by MCP tool signatures.

Pagination envelope is shared across all ``list_*`` / ``search_*`` tools.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_LIMIT = 100


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool


def clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > MAX_LIMIT:
        return MAX_LIMIT
    return limit


class EditPromptInput(BaseModel):
    """Edit a system prompt. ``reason`` is mandatory and stored as the
    version's changelog — every edit bumps the version."""

    agent_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    reason: str = Field(min_length=3, description="Why this edit was made.")
    author: str = Field(default="mcp")


class RollbackPromptInput(BaseModel):
    agent_id: str = Field(min_length=1)
    target_version: int = Field(ge=1)
    reason: str = Field(min_length=3)
    author: str = Field(default="mcp")


class RunFilter(BaseModel):
    agent_id: str | None = None
    status: str | None = None
    model: str | None = None
    q: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int = 20
    offset: int = 0


JsonDict = dict[str, Any]
