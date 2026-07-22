"""Request/response models for the /runs API."""

from __future__ import annotations
from typing import Any, Literal

from agentbox.core.data.payload_types import UsagePayload
from pydantic import BaseModel



class CreateRunBody(BaseModel):
    agent: str
    input: str | None = None
    variables: dict[str, str] | None = None
    session_id: str | None = None
    workspace: str | None = None
    timeout_seconds: int | None = None
    webhook_url: str | None = None
    runner: str | None = None
    backend: str | None = None
    runner_profile: str | None = None
    runner_config: dict[str, Any] | None = None
    runner_embedded: bool = False
    fresh_workspace: bool = False
    session_mode: Literal["headless", "persistent"] | None = None


class CompleteRunBody(BaseModel):
    ok: bool
    output: str | None = None
    error: str | None = None
    usage: UsagePayload | None = None


class SnapshotBody(BaseModel):
    rendered_prompt: dict
    variables: dict
    response_raw: str
    validation_status: str = "ok"
    validation_errors: list[str] = []
    composition_snapshot: dict | None = None


class PostOutcomeBody(BaseModel):
    status: str
    error_kind: str | None = None
    errors: list[dict] | None = None


class RunCommentBody(BaseModel):
    author: str = "api"
    body: str


class RunRatingBody(BaseModel):
    rating: int


__all__ = [
    "CompleteRunBody",
    "CreateRunBody",
    "PostOutcomeBody",
    "RunCommentBody",
    "RunRatingBody",
    "SnapshotBody",
]
