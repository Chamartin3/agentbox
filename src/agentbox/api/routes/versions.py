"""Agent versioning endpoints — read, diff, comment, rate, create, rollback.

Phase 6a: read-only (list, get, diff, comments, ratings).
Phase 6b: write-back (POST new version, rollback).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_loader, get_store

router = APIRouter(prefix="/api/agents/{agent_id}/versions", tags=["versions"])


# ---------------------------------------------------------------------------
# Read — Phase 6a
# ---------------------------------------------------------------------------


@router.get("")
def list_agent_versions(agent_id: str) -> dict:
    store = get_store()
    agent = store.get_agent_def(agent_id) or get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    versions = store.list_versions(agent_id)
    active = store.get_active_version(agent_id)
    latest = store.latest_version(agent_id)
    # Fall back to latest when no active pointer exists (legacy agents
    # imported before active_agent_versions was populated).
    if active is None and latest is not None:
        active = latest
    active_id = active["id"] if active else None
    active_version_num = active["version"] if active else None
    enriched = [
        {
            "id": v["id"],
            "version": v["version"],
            "author": v["author"],
            "changelog": v["changelog"],
            "is_legacy": v.get("is_legacy", False),
            "is_draft": bool(v.get("is_draft", False)),
            "is_active": v["id"] == active_id,
            "created_at": v["created_at"],
        }
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
def get_agent_version(agent_id: str, version: int) -> dict:
    store = get_store()
    if store.get_agent_def(agent_id) is None and get_loader().get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    v = store.get_version(agent_id, version)
    if v is None:
        raise HTTPException(404, f"version {version} not found")
    rating = store.get_rating(v["id"])
    comments = store.list_comments(v["id"])
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
def diff_agent_versions(agent_id: str, a: int, b: int) -> dict:
    store = get_store()
    if store.get_agent_def(agent_id) is None and get_loader().get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    try:
        return store.diff_versions(agent_id, a, b)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------
# Comments — Phase 6a
# ---------------------------------------------------------------------------


class CommentBody(BaseModel):
    author: str = "api"
    body: str


@router.post("/{version}/comments")
def add_comment(agent_id: str, version: int, body: CommentBody) -> dict:
    store = get_store()
    if store.get_agent_def(agent_id) is None and get_loader().get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    v = store.get_version(agent_id, version)
    if v is None:
        raise HTTPException(404, f"version {version} not found")
    return store.add_comment(v["id"], body.author, body.body)


# ---------------------------------------------------------------------------
# Ratings — Phase 6a
# ---------------------------------------------------------------------------


class RatingBody(BaseModel):
    rating: int
    rater: str = "api"


@router.put("/{version}/rating")
def set_rating(agent_id: str, version: int, body: RatingBody) -> dict:
    store = get_store()
    if store.get_agent_def(agent_id) is None and get_loader().get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    v = store.get_version(agent_id, version)
    if v is None:
        raise HTTPException(404, f"version {version} not found")
    try:
        return store.set_rating(v["id"], body.rating, body.rater)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------------------
# Write-back — Phase 6b
# ---------------------------------------------------------------------------


class NewVersionBody(BaseModel):
    content_snapshot: str
    prompt_snapshot: str = ""
    author: str = "api"
    changelog: str = ""


@router.post("")
def create_agent_version(agent_id: str, body: NewVersionBody) -> dict:
    """Create a new version from a full agent definition snapshot.

    Phase 6b: caller is responsible for writing the agent file to disk
    first (via Plan 04's writer). This endpoint only records the version row.
    """
    loader = get_loader()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
    return store.create_version(
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
def save_prompt_revision(agent_id: str, body: PromptRevisionBody) -> dict:
    """Create a new agent_version with edited prompt_content.

    Every call creates a new row — the "draft slot" reuse pattern of the
    legacy prompt_versions table does not apply. If ``activate`` is true
    (default), the new version is also set as active.
    """
    store = get_store()
    loader = get_loader()
    if store.get_agent_def(agent_id) is None and loader.get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    try:
        result = store.save_prompt_revision(
            agent_id,
            prompt_content=body.prompt_content,
            author=body.author,
            changelog=body.changelog,
            activate=body.activate,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


# Rollback is handled by the canonical endpoint in agents.py
# (POST /api/agents/{agent_id}/versions/{version}/rollback with {reason, author}).
