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
    loader = get_loader()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
    versions = store.list_versions(agent_id)
    enriched = []
    for v in versions:
        rating = store.get_rating(v["id"])
        comments = store.list_comments(v["id"])
        enriched.append(
            {
                "id": v["id"],
                "version": v["version"],
                "author": v["author"],
                "changelog": v["changelog"],
                "is_legacy": v["is_legacy"],
                "created_at": v["created_at"],
                "has_comments": len(comments) > 0,
                "rating": rating["rating"] if rating else None,
            }
        )
    latest = store.latest_version(agent_id)
    return {
        "agent_id": agent_id,
        "latest_version": latest["version"] if latest else None,
        "versions": enriched,
    }


@router.get("/{version}")
def get_agent_version(agent_id: str, version: int) -> dict:
    loader = get_loader()
    if loader.get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
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
    loader = get_loader()
    if loader.get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
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
    loader = get_loader()
    if loader.get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
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
    loader = get_loader()
    if loader.get(agent_id) is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
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
        source_format=(
            agent.source_format.value if agent.source_format else "unknown"
        ),
        content_snapshot=body.content_snapshot,
        prompt_snapshot=body.prompt_snapshot,
        content_hash="",
        author=body.author,
        changelog=body.changelog,
    )


class RollbackBody(BaseModel):
    author: str = "api"


@router.post("/{version}/rollback")
def rollback_agent_version(agent_id: str, version: int, body: RollbackBody) -> dict:
    """Restore content to a previous version (creates a new version on top)."""
    loader = get_loader()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
    target = store.get_version(agent_id, version)
    if target is None:
        raise HTTPException(404, f"version {version} not found")
    return store.create_version(
        agent_id=agent_id,
        source_path=target["source_path"],
        source_format=target["source_format"],
        content_snapshot=target["content_snapshot"],
        prompt_snapshot=target["prompt_snapshot"],
        content_hash=target["content_hash"],
        author=body.author,
        changelog=f"Rollback to version {version}",
    )
