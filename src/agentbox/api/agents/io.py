"""DB-only write endpoints under /api/agents."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_agent_service
from agentbox.core.service.agents import AgentServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# PATCH /api/agents/{id} — DB-first config save
# ---------------------------------------------------------------------------


class _RunnerPatch(BaseModel):
    kind: str | None = None
    model: str | None = None
    mcp_config_path: str | None = None
    allowed_tools: list[str] | None = None
    extra_args: list[str] | None = None
    timeout_seconds: int | None = None
    agent_module: str | None = None
    output_schema_path: str | None = None
    output_validation_engine: str | None = None
    max_validation_retries: int | None = None
    max_error_retries: int | None = None


class _CompositionPatch(BaseModel):
    system: str | None = None
    user_template: str | None = None
    input_schema: str | None = None
    output_schema: str | None = None
    transport: str | None = None
    output_validation: str | None = None
    references: list[dict | str] | None = None


class AgentPatch(BaseModel):
    """Editable subset of an AgentDef. All fields optional."""

    description: str | None = None
    session_mode: str | None = None
    workspace: str | None = None
    tags: list[str] | None = None
    tools: list[str] | None = None
    webhook_url: str | None = None
    headless: bool | None = None
    runner: _RunnerPatch | None = None
    composition: _CompositionPatch | None = None


@router.patch("/{agent_id}")
def patch_agent(agent_id: str, body: AgentPatch) -> dict:
    """DB-first config save. Creates a new ``agent_versions`` row.

    On-disk files are not written by this endpoint — use
    ``POST /api/agents/{id}/export`` for that.
    """
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        updated = get_agent_service().patch_agent_config(agent_id, patch)
    except AgentServiceError as exc:
        detail: object = (
            exc.detail if exc.code == "empty_patch" else {"code": exc.code, "detail": exc.detail}
        )
        raise HTTPException(exc.status_code, detail) from exc
    return {"agent": updated.model_dump()}
