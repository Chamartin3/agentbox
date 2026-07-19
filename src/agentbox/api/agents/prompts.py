"""Prompt read/write endpoints with versioning, scoped per agent.

Thin HTTP layer: delegates to ``AgentService`` prompt-doc methods and maps
``AgentNotFound`` / ``PromptError`` / ``ValueError`` to HTTPException.
"""

from __future__ import annotations

from typing import NoReturn, TypedDict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_agent_service
from agentbox.core.data.payload_types import PromptVersionDetail, PromptVersionListResult
from agentbox.core.service.agents import AgentNotFound, PromptError

router = APIRouter(prefix="/api", tags=["prompts"])


class _PromptDocResult(TypedDict):
    """Response shape of prompt read/write endpoints (from PromptDoc.__dict__)."""

    path: str
    content: str
    size: int
    mtime: str


def _raise_prompt_error(exc: PromptError) -> NoReturn:
    raise HTTPException(400, {"code": exc.code, "detail": exc.detail}) from exc


# ---------------------------------------------------------------------------
# Current prompt
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/prompt")
def get_prompt(agent_id: str) -> _PromptDocResult:
    try:
        doc = get_agent_service().get_prompt_doc(agent_id)
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return {
        "path": doc.path,
        "content": doc.content,
        "size": doc.size,
        "mtime": doc.mtime,
    }


class PromptBody(BaseModel):
    content: str


@router.put("/agents/{agent_id}/prompt")
def put_prompt(agent_id: str, body: PromptBody) -> _PromptDocResult:
    """Capture a new committed prompt version if content changed."""
    try:
        doc = get_agent_service().put_prompt_doc(agent_id, body.content)
    except AgentNotFound as exc:
        raise HTTPException(404) from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return {
        "path": doc.path,
        "content": doc.content,
        "size": doc.size,
        "mtime": doc.mtime,
    }


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/prompt/versions")
def list_versions(agent_id: str) -> PromptVersionListResult:
    try:
        return get_agent_service().prompt_version_list(agent_id)
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc


@router.get("/agents/{agent_id}/prompt/versions/{version}")
def get_version(agent_id: str, version: int) -> PromptVersionDetail | None:
    try:
        payload = get_agent_service().prompt_version_detail(agent_id, version)
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    if payload is None:
        raise HTTPException(404, f"version {version} not found")
    return payload


# ---------------------------------------------------------------------------
# Draft / publish / rollback
# ---------------------------------------------------------------------------


class DraftBody(BaseModel):
    content: str
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/draft")
def save_draft(agent_id: str, body: DraftBody) -> _PromptDocResult:
    try:
        doc = get_agent_service().save_prompt_draft_doc(
            agent_id, body.content, author=body.author
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    return {
        "path": doc.path,
        "content": doc.content,
        "size": doc.size,
        "mtime": doc.mtime,
    }


class PublishBody(BaseModel):
    changelog: str = ""
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/publish")
def publish_prompt(agent_id: str, body: PublishBody) -> _PromptDocResult:
    try:
        doc = get_agent_service().publish_prompt_doc(
            agent_id, changelog=body.changelog, author=body.author
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(400, {"code": "no_draft", "detail": str(exc)}) from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return {
        "path": doc.path,
        "content": doc.content,
        "size": doc.size,
        "mtime": doc.mtime,
    }


class RollbackBody(BaseModel):
    target_version: int
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/rollback")
def rollback_prompt(agent_id: str, body: RollbackBody) -> _PromptDocResult:
    try:
        doc = get_agent_service().rollback_prompt_doc(
            agent_id, body.target_version, author=body.author
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(
            400, {"code": "rollback_error", "detail": str(exc)}
        ) from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return {
        "path": doc.path,
        "content": doc.content,
        "size": doc.size,
        "mtime": doc.mtime,
    }
