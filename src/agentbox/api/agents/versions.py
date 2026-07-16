"""Agent versioning endpoints — read, diff, comment, rate, create, rollback.

Transport-only: parses bodies, calls store / service, maps domain errors
to HTTP. The repeated agent-existence guard lives in
:func:`agentbox.core.service.agents.require_agent_exists`.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_agent_service
from agentbox.core.data.payload_types import AgentDiffResult
from agentbox.core.service import (
    AgentVersionCommentRow,
    AgentVersionRatingRow,
    AgentVersionRow,
)
from agentbox.core.service.agents import AgentNotFound

router = APIRouter(prefix="/api/agents/{agent_id}/versions", tags=["versions"])


class _VersionSummaryItem(TypedDict):
    """One entry in the versions list."""

    id: int
    version: int
    author: str
    changelog: str
    is_legacy: bool
    is_active: bool
    created_at: str


class _VersionListResult(TypedDict):
    """Response shape of GET /api/agents/{agent_id}/versions."""

    agent_id: str
    latest_version: int | None
    active_version: int | None
    active_version_id: int | None
    versions: list[_VersionSummaryItem]


class _VersionDetailResult(TypedDict):
    """Response shape of GET /api/agents/{agent_id}/versions/{version}."""

    id: int
    version: int
    author: str
    changelog: str
    source_path: str
    source_format: str
    content_snapshot: str
    prompt_snapshot: str
    content_hash: str
    is_legacy: bool
    created_at: str
    rating: NotRequired[AgentVersionRatingRow | None]
    comments: NotRequired[list[AgentVersionCommentRow]]


def _require_agent(agent_id: str) -> None:
    try:
        get_agent_service().require_agent_exists(agent_id)
    except AgentNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("")
def list_agent_versions(agent_id: str) -> _VersionListResult:
    _require_agent(agent_id)
    svc = get_agent_service()
    versions = svc.list_versions(agent_id)
    active = svc.effective_active_version(agent_id)
    latest = svc.latest_version(agent_id)
    active_id = active["id"] if active else None
    active_version_num = active["version"] if active else None
    enriched: list[_VersionSummaryItem] = [
        _VersionSummaryItem(
            id=v["id"],
            version=v["version"],
            author=v["author"],
            changelog=v["changelog"],
            is_legacy=v.get("is_legacy", False),
            is_active=v["id"] == active_id,
            created_at=v["created_at"],
        )
        for v in versions
    ]
    return {
        "agent_id": agent_id,
        "latest_version": latest["version"] if latest else None,
        "active_version": active_version_num,
        "active_version_id": active_id,
        "versions": enriched,
    }


@router.get("/{version}")
def get_agent_version(agent_id: str, version: int) -> _VersionDetailResult:
    _require_agent(agent_id)
    svc = get_agent_service()
    v = svc.get_version(agent_id, version)
    if v is None:
        raise HTTPException(404, f"version {version} not found")
    rating = svc.get_rating(v["id"])
    comments = svc.list_comments(v["id"])
    return {
        "id": v["id"],
        "version": v["version"],
        "author": v["author"],
        "changelog": v["changelog"],
        "source_path": v["source_path"],
        "source_format": v["source_format"],
        "content_snapshot": v["content_snapshot"],
        "prompt_snapshot": v["prompt_snapshot"],
        "content_hash": v["content_hash"],
        "is_legacy": v["is_legacy"],
        "created_at": v["created_at"],
        "rating": rating,
        "comments": comments,
    }


@router.get("/{a}/diff/{b}")
def diff_agent_versions(agent_id: str, a: int, b: int) -> AgentDiffResult:
    _require_agent(agent_id)
    try:
        return get_agent_service().diff_versions(agent_id, a, b)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class CommentBody(BaseModel):
    author: str = "api"
    body: str


@router.post("/{version}/comments")
def add_comment(agent_id: str, version: int, body: CommentBody) -> AgentVersionCommentRow:
    _require_agent(agent_id)
    svc = get_agent_service()
    v = svc.get_version(agent_id, version)
    if v is None:
        raise HTTPException(404, f"version {version} not found")
    return svc.add_comment(v["id"], body.author, body.body)


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------


class RatingBody(BaseModel):
    rating: int
    rater: str = "api"


@router.put("/{version}/rating")
def set_rating(agent_id: str, version: int, body: RatingBody) -> AgentVersionRatingRow:
    _require_agent(agent_id)
    svc = get_agent_service()
    v = svc.get_version(agent_id, version)
    if v is None:
        raise HTTPException(404, f"version {version} not found")
    try:
        return svc.set_rating(v["id"], body.rating, body.rater)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------------------
# Write-back
# ---------------------------------------------------------------------------


class NewVersionBody(BaseModel):
    content_snapshot: str
    prompt_snapshot: str = ""
    author: str = "api"
    changelog: str = ""


@router.post("")
def create_agent_version(agent_id: str, body: NewVersionBody) -> AgentVersionRow:
    """Create a new version from a full agent definition snapshot."""
    svc = get_agent_service()
    agent = svc.get_agent_def(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    return svc.create_version(
        agent_id=agent_id,
        source_path=str(agent.source_path) if agent.source_path else "",
        source_format=(agent.source_format.value if agent.source_format else "unknown"),
        content_snapshot=body.content_snapshot,
        prompt_snapshot=body.prompt_snapshot,
        content_hash="",
        author=body.author,
        changelog=body.changelog,
    )


class PromptRevisionBody(BaseModel):
    prompt_content: str
    changelog: str = ""
    author: str = "ui"
    activate: bool = True


@router.post("/prompt-revision", status_code=201)
def save_prompt_revision(agent_id: str, body: PromptRevisionBody) -> AgentVersionRow:
    """Create a new agent_version with edited prompt_content.

    Every call creates a new row — the "draft slot" reuse pattern of the
    legacy prompt_versions table does not apply. If ``activate`` is true
    (default), the new version is also set as active.
    """
    _require_agent(agent_id)
    try:
        return get_agent_service().save_prompt_revision(
            agent_id,
            prompt_content=body.prompt_content,
            author=body.author,
            changelog=body.changelog,
            activate=body.activate,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# Rollback is handled by the canonical endpoint in agents.py
# (POST /api/agents/{agent_id}/versions/{version}/rollback with {reason, author}).
