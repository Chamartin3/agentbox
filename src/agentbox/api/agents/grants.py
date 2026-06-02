"""REST endpoints for per-agent tool grant management (Plan 19)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.service import SessionStore

router = APIRouter(prefix="/api/agents", tags=["agent-tool-grants"])


class GrantBody(BaseModel):
    tool_name: str = Field(..., min_length=1)
    changelog: str = Field(..., min_length=3)
    actor: str | None = None


class RevokeBody(BaseModel):
    changelog: str = Field(..., min_length=3)
    actor: str | None = None


@router.get("/{agent_id}/tool_grants")
def list_grants(
    agent_id: str,
    include_revoked: bool = False,
    store: Annotated[SessionStore, Depends(get_store)] = ...,  # pyright: ignore[reportArgumentType]
):
    return {
        "items": store.list_agent_tool_grants(agent_id, include_revoked=include_revoked)
    }


@router.post("/{agent_id}/tool_grants", status_code=201)
def grant_tool(
    agent_id: str,
    body: GrantBody,
    store: Annotated[SessionStore, Depends(get_store)] = ...,  # pyright: ignore[reportArgumentType]
):
    try:
        return store.grant_agent_tool(
            agent_id=agent_id,
            tool_name=body.tool_name,
            changelog=body.changelog,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{agent_id}/tool_grants/{tool_name}", status_code=204)
def revoke_tool(
    agent_id: str,
    tool_name: str,
    body: RevokeBody,
    store: Annotated[SessionStore, Depends(get_store)] = ...,  # pyright: ignore[reportArgumentType]
):
    try:
        store.revoke_agent_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=body.changelog,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
