"""Endpoints for creating agents and managing version bundle files (DB-only agents)."""

from __future__ import annotations

import hashlib
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.agent.config import build_config_json_payload
from agentbox.core.data.manifest import (
    AgentDef,
    CompositionConfig,
    RunnerSpec,
    WorkspaceDef,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentCreateRequest(BaseModel):
    """Request body for creating a new DB-only agent."""

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
    """Request body for uploading a file to a version."""

    kind: Literal[
        "output_schema", "input_schema", "user_template", "system", "reference"
    ]
    name: str
    content: str


class AgentCreateResponse(BaseModel):
    """Response for successful agent creation."""

    agent_id: str
    version: int
    version_id: int
    is_draft: bool


class FileUploadResponse(BaseModel):
    """Response for successful file upload."""

    file_id: int
    sha256: str
    size: int


@router.post("", status_code=201)
def create_agent(req: AgentCreateRequest) -> AgentCreateResponse:
    """Create a new agent with v1 draft.

    Request body specifies agent configuration (runner, prompt, composition, etc.).
    The agent is created as a v1 draft in the DB with no on-disk backing file.
    """
    store = get_store()

    # Construct AgentDef from request
    agent_def = AgentDef(
        id=req.id,
        description=req.description,
        runner=req.runner,
        prompt=req.prompt,
        composition=req.composition,
        tools=req.tools or [],
        tags=req.tags or [],
        workspace=req.workspace,
        session_mode=req.session_mode or "headless",
        webhook_url=req.webhook_url,
        source_path=None,
        source_format=None,
    )

    # Create version in DB
    try:
        version_record = store.create_agent(
            agent_id=req.id,
            config_json={
                **agent_def.model_dump(mode="json", exclude_none=True),
                **build_config_json_payload(agent_def),
            },
            prompt_content=req.prompt,
            author=req.author,
            changelog=req.changelog,
            source="ui",
            source_path=None,
            source_format=None,
            sync_mode="off",
            export_to_disk=False,
        )
    except ValueError as exc:
        raise HTTPException(
            409, {"code": "already_exists", "detail": str(exc)}
        ) from exc

    return AgentCreateResponse(
        agent_id=req.id,
        version=version_record["version"],
        version_id=version_record["id"],
        is_draft=bool(version_record.get("is_draft")),
    )


@router.post("/{agent_id}/versions/{version}/files", status_code=201)
def upload_file(
    agent_id: str, version: int, req: FileUploadRequest
) -> FileUploadResponse:
    """Upload a file to a draft version.

    File must be uploaded to a draft version (is_draft=True).
    Returns 409 if the version is not a draft or if a file with the same
    sha256 already exists.
    """
    store = get_store()

    # Fetch version
    version_record = store.get_version(agent_id, version)
    if version_record is None:
        raise HTTPException(404, {"code": "version_not_found"})

    # Check draft status
    if not version_record.get("is_draft"):
        raise HTTPException(
            409, {"code": "not_draft", "detail": "cannot modify published version"}
        )

    # Compute sha256
    sha256_hash = hashlib.sha256(req.content.encode()).hexdigest()

    # Check for collisions (sha256 or path)
    files = store.list_version_files(version_record["id"])
    for f in files:
        if f.get("sha256") == sha256_hash:
            raise HTTPException(409, {"code": "duplicate_sha256"})
        if f.get("relative_path") == req.name:
            raise HTTPException(409, {"code": "duplicate_path"})

    # Insert file
    store.insert_version_files(
        version_record["id"],
        [
            {
                "relative_path": req.name,
                "kind": req.kind,
                "content": req.content,
                "sha256": sha256_hash,
            }
        ],
    )

    # Fetch the inserted file to get its ID
    files = store.list_version_files(version_record["id"])
    inserted_file = next((f for f in files if f.get("sha256") == sha256_hash), None)

    if inserted_file is None:
        raise HTTPException(500, {"code": "file_insert_failed"})

    return FileUploadResponse(
        file_id=inserted_file["id"],
        sha256=sha256_hash,
        size=len(req.content),
    )


@router.delete("/{agent_id}/versions/{version}/files/{file_id}", status_code=204)
def delete_file(agent_id: str, version: int, file_id: int) -> None:
    """Delete a file from a draft version.

    Returns 404 if version or file is missing.
    Returns 409 if version is not a draft.
    """
    store = get_store()

    # Fetch version
    version_record = store.get_version(agent_id, version)
    if version_record is None:
        raise HTTPException(404, {"code": "version_not_found"})

    # Check draft status
    if not version_record.get("is_draft"):
        raise HTTPException(409, {"code": "not_draft"})

    # Check file exists
    files = store.list_version_files(version_record["id"])
    if not any(f.get("id") == file_id for f in files):
        raise HTTPException(404, {"code": "file_not_found"})

    # Delete file
    store.delete_version_file(file_id)
