"""Endpoints for creating agents and managing version bundle files (DB-only agents).

Transport-only: parses request bodies, calls
:mod:`agentbox.core.service.agents`, maps domain errors to HTTP.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_agent_service
from agentbox.core.service import CompositionConfig, RunnerSpec, WorkspaceDef
from agentbox.core.service.agents import (
    AgentAlreadyExists,
    DuplicateVersionFile,
    VersionFileNotFound,
    VersionNotDraft,
    VersionNotFound,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentCreateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    description: str
    runner: RunnerSpec
    prompt: str | None = None
    composition: CompositionConfig | None = None
    tools: list[str] | None = None
    tags: list[str] | None = None
    workspace: WorkspaceDef | None = None
    session_mode: Literal["fresh", "resume"] | None = None
    webhook_url: str | None = None
    author: str = Field(..., min_length=1)
    changelog: str = Field(..., min_length=3)


class FileUploadRequest(BaseModel):
    kind: Literal[
        "output_schema", "input_schema", "user_template", "system", "reference"
    ]
    name: str
    content: str


class AgentCreateResponse(BaseModel):
    agent_id: str
    version: int
    version_id: int


class FileUploadResponse(BaseModel):
    file_id: int
    sha256: str
    size: int


@router.post("", status_code=201)
def create_agent(req: AgentCreateRequest) -> AgentCreateResponse:
    try:
        version_record = get_agent_service().create_agent_record(
            agent_id=req.id,
            description=req.description,
            runner=req.runner,
            prompt=req.prompt,
            composition=req.composition,
            tools=req.tools,
            tags=req.tags,
            workspace=req.workspace,
            session_mode=req.session_mode,
            webhook_url=req.webhook_url,
            author=req.author,
            changelog=req.changelog,
        )
    except AgentAlreadyExists as exc:
        raise HTTPException(
            409, {"code": "already_exists", "detail": str(exc)}
        ) from exc
    return AgentCreateResponse(
        agent_id=req.id,
        version=version_record["version"],
        version_id=version_record["id"],
    )


@router.post("/{agent_id}/versions/{version}/files", status_code=201)
def upload_file(
    agent_id: str, version: int, req: FileUploadRequest
) -> FileUploadResponse:
    try:
        result = get_agent_service().upload_version_file(
            agent_id=agent_id,
            version=version,
            kind=req.kind,
            name=req.name,
            content=req.content,
        )
    except VersionNotFound:
        raise HTTPException(404, {"code": "version_not_found"}) from None
    except VersionNotDraft as exc:
        raise HTTPException(
            409, {"code": "not_draft", "detail": str(exc)}
        ) from exc
    except DuplicateVersionFile as exc:
        raise HTTPException(409, {"code": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(500, {"code": str(exc)}) from exc
    return FileUploadResponse(
        file_id=result["file"]["id"],
        sha256=result["sha256"],
        size=result["size"],
    )


@router.delete("/{agent_id}/versions/{version}/files/{file_id}", status_code=204)
def delete_file(agent_id: str, version: int, file_id: int) -> None:
    try:
        get_agent_service().remove_version_file(
            agent_id=agent_id,
            version=version,
            file_id=file_id,
        )
    except VersionNotFound:
        raise HTTPException(404, {"code": "version_not_found"}) from None
    except VersionNotDraft:
        raise HTTPException(409, {"code": "not_draft"}) from None
    except VersionFileNotFound:
        raise HTTPException(404, {"code": "file_not_found"}) from None
