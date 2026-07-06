"""Prompt read/write endpoints with versioning, scoped per agent.

Thin HTTP layer: delegates to ``core.service.agents.prompts`` and maps
``AgentNotFound`` / ``PromptError`` / ``ValueError`` to HTTPException.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_db, get_settings
from agentbox.core.data.payload_types import PromptVersionDetail, PromptVersionListResult
from agentbox.core.service.agents import prompts as prompts_service
from agentbox.core.service.agents.prompts import AgentNotFound, PromptError

router = APIRouter(prefix="/api", tags=["prompts"])


def _raise_prompt_error(exc: PromptError) -> NoReturn:
    raise HTTPException(400, {"code": exc.code, "detail": exc.detail}) from exc


# ---------------------------------------------------------------------------
# Current prompt
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/prompt")
def get_prompt(agent_id: str) -> dict:
    try:
        db = get_db()
        doc = prompts_service.get_prompt(
            agent_id,
            agent_defs=db.agent_defs,
            agent_versions=db.agent_versions,
            prompt_versions=db.prompt_versions,
            project_root=get_settings().project_root,
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return doc.__dict__


class PromptBody(BaseModel):
    content: str


@router.put("/agents/{agent_id}/prompt")
def put_prompt(agent_id: str, body: PromptBody) -> dict:
    """Write prompt to disk and create a new committed version if changed."""
    try:
        db = get_db()
        doc = prompts_service.put_prompt(
            agent_id,
            body.content,
            agent_defs=db.agent_defs,
            prompt_versions=db.prompt_versions,
            project_root=get_settings().project_root,
        )
    except AgentNotFound as exc:
        raise HTTPException(404) from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return doc.__dict__


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/prompt/versions")
def list_versions(agent_id: str) -> PromptVersionListResult:
    try:
        db = get_db()
        return prompts_service.list_versions(
            agent_id,
            agent_defs=db.agent_defs,
            prompt_versions=db.prompt_versions,
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc


@router.get("/agents/{agent_id}/prompt/versions/{version}")
def get_version(agent_id: str, version: int) -> PromptVersionDetail | None:
    try:
        db = get_db()
        payload = prompts_service.get_version(
            agent_id,
            version,
            agent_defs=db.agent_defs,
            prompt_versions=db.prompt_versions,
        )
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
def save_draft(agent_id: str, body: DraftBody) -> dict:
    try:
        db = get_db()
        doc = prompts_service.save_draft(
            agent_id,
            body.content,
            agent_defs=db.agent_defs,
            prompt_versions=db.prompt_versions,
            author=body.author,
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    return doc.__dict__


class PublishBody(BaseModel):
    changelog: str = ""
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/publish")
def publish_prompt(agent_id: str, body: PublishBody) -> dict:
    try:
        db = get_db()
        doc = prompts_service.publish(
            agent_id,
            agent_defs=db.agent_defs,
            prompt_versions=db.prompt_versions,
            project_root=get_settings().project_root,
            changelog=body.changelog,
            author=body.author,
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(400, {"code": "no_draft", "detail": str(exc)}) from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return doc.__dict__


class RollbackBody(BaseModel):
    target_version: int
    author: str = "system"


@router.post("/agents/{agent_id}/prompt/rollback")
def rollback_prompt(agent_id: str, body: RollbackBody) -> dict:
    try:
        db = get_db()
        doc = prompts_service.rollback(
            agent_id,
            body.target_version,
            agent_defs=db.agent_defs,
            prompt_versions=db.prompt_versions,
            project_root=get_settings().project_root,
            author=body.author,
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(
            400, {"code": "rollback_error", "detail": str(exc)}
        ) from exc
    except PromptError as exc:
        _raise_prompt_error(exc)
    return doc.__dict__
