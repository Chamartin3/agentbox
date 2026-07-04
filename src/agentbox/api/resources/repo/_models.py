"""Shared models and helpers for repo-resource endpoints."""

from __future__ import annotations

from typing import Literal, Never

from fastapi import HTTPException
from pydantic import BaseModel, Field

from agentbox.core.data.constants import ResourceType


def _raise_not_found(detail: str = "resource not found") -> Never:
    raise HTTPException(status_code=404, detail=detail)


class CreateResourceBody(BaseModel):
    slug: str
    type: ResourceType
    display_name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class UpdateResourceBody(BaseModel):
    display_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class HostPathImportBody(BaseModel):
    path: str
    recursive: bool = True
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    changelog: str = Field(..., min_length=3)
    draft: bool = False
    actor: str | None = None


class PublishBody(BaseModel):
    reason: str = Field(..., min_length=3)
    actor: str | None = None


class RollbackBody(BaseModel):
    target_version: int
    reason: str = Field(..., min_length=3)
    actor: str | None = None


class ValidateBody(BaseModel):
    sample: dict | list | str | int | float | bool | None
    direction: Literal["input", "output"] = "input"
