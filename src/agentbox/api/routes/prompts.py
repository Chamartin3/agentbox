"""Prompt read/write endpoints with versioning, scoped per agent."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core import prompts

router = APIRouter(prefix="/api", tags=["prompts"])


# ---------------------------------------------------------------------------
# Current prompt
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/prompt")
def get_prompt(agent_id: str) -> dict:
    agent = get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    try:
        doc = prompts.read_versioned(agent, get_settings().project_root, get_store())
    except prompts.PromptError as exc:
        raise HTTPException(400, {"code": exc.code, "detail": exc.detail}) from exc
    return doc.__dict__


class PromptBody(BaseModel):
    content: str


@router.put("/agents/{agent_id}/prompt")
def put_prompt(agent_id: str, body: PromptBody) -> dict:
    """Write prompt to disk and create a new committed version if changed."""
    agent = get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404)
    try:
        doc = prompts.write(agent, get_settings().project_root, body.content)
    except prompts.PromptError as exc:
        raise HTTPException(400, {"code": exc.code, "detail": exc.detail}) from exc

    # Capture every disk write as a versioned entry when content changed.
    # No-op if the content matches the latest committed version.
    get_store().sync_prompt_from_disk(agent_id, body.content, author="api")

    return doc.__dict__


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/prompt/versions")
def list_versions(agent_id: str) -> dict:
    agent = get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
    versions = store.list_prompt_versions(agent_id)
    committed = [v for v in versions if not v["is_draft"]]
    drafts = [v for v in versions if v["is_draft"]]
    return {
        "agent_id": agent_id,
        "active_version": committed[0]["version"] if committed else None,
        "draft_version": drafts[0]["version"] if drafts else None,
        "versions": [
            {
                "version": v["version"],
                "is_draft": bool(v["is_draft"]),
                "created_at": v["created_at"],
                "author": v["author"],
                "changelog": v["changelog"],
                "size": len(v["content"].encode("utf-8")),
            }
            for v in versions
        ],
    }


@router.get("/agents/{agent_id}/prompt/versions/{version}")
def get_version(agent_id: str, version: int) -> dict:
    agent = get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
    v = store.get_prompt_version(agent_id, version)
    if v is None:
        raise HTTPException(404, f"version {version} not found")
    return {
        "version": v["version"],
        "is_draft": bool(v["is_draft"]),
        "created_at": v["created_at"],
        "author": v["author"],
        "changelog": v["changelog"],
        "content": v["content"],
        "size": len(v["content"].encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# Draft / publish / rollback
# ---------------------------------------------------------------------------


class DraftBody(BaseModel):
    content: str
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/draft")
def save_draft(agent_id: str, body: DraftBody) -> dict:
    agent = get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    store = get_store()
    doc = prompts.save_draft(agent_id, store, body.content, author=body.author)
    return doc.__dict__


class PublishBody(BaseModel):
    changelog: str = ""
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/publish")
def publish_prompt(agent_id: str, body: PublishBody) -> dict:
    agent = get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    try:
        doc = prompts.publish(
            agent_id,
            get_store(),
            get_settings().project_root,
            agent=agent,
            changelog=body.changelog,
            author=body.author,
        )
    except ValueError as exc:
        raise HTTPException(400, {"code": "no_draft", "detail": str(exc)}) from exc
    except prompts.PromptError as exc:
        raise HTTPException(400, {"code": exc.code, "detail": exc.detail}) from exc
    return doc.__dict__


class RollbackBody(BaseModel):
    target_version: int
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/rollback")
def rollback_prompt(agent_id: str, body: RollbackBody) -> dict:
    agent = get_loader().get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    try:
        doc = prompts.rollback(
            agent_id,
            get_store(),
            get_settings().project_root,
            target_version=body.target_version,
            agent=agent,
            author=body.author,
        )
    except ValueError as exc:
        raise HTTPException(
            400, {"code": "rollback_error", "detail": str(exc)}
        ) from exc
    except prompts.PromptError as exc:
        raise HTTPException(400, {"code": exc.code, "detail": exc.detail}) from exc
    return doc.__dict__
