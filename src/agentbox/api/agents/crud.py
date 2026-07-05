"""/agents endpoints — list definitions, fetch one, workspace info."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_agent_service, get_engine_service
from agentbox.api.runs.webhooks import schedule_agent_event_webhook
from agentbox.core.service import RunnerProfile
from agentbox.core.service.engines.service import EngineService, ProfileNotFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents(include_disabled: bool = False) -> list[dict]:
    """List agents from the DB (one row per agent_id, latest version).

    DB-as-source-of-truth: every agent that has ever been imported into
    ``agent_versions`` appears here. Enrichment (run counts, bound
    runner profile, resolved workspace) is owned by
    ``core.service.agents.list_agents_enriched``. Pass
    ``?include_disabled=true`` to surface agents that have been disabled
    (each carries a ``disabled_at`` timestamp).
    """
    return get_agent_service().list_agents_enriched(include_disabled=include_disabled)


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict:
    detail = get_agent_service().get_agent_detail(agent_id)
    if detail is None:
        raise HTTPException(404)
    return detail


# ---------------------------------------------------------------------------
# Workspace assignment
# ---------------------------------------------------------------------------


class WorkspaceBody(BaseModel):
    workspace: str | None = None


@router.patch("/{agent_id}/workspace")
def set_workspace(agent_id: str, body: WorkspaceBody) -> dict:
    """Update an agent's workspace assignment.

    Workspace assignment is stored in the DB via the agent version config.
    Use the agent version API to update config_json.workspace directly.
    """
    agent = get_agent_service().resolve_agent(agent_id)
    if agent is None:
        raise HTTPException(404)
    return {
        "agent_id": agent_id,
        "workspace": agent.workspace or body.workspace,
    }


# ---------------------------------------------------------------------------
# Lifecycle — publish, branch draft, rollback
# ---------------------------------------------------------------------------


class PublishRequest(BaseModel):
    reason: str = Field(default="activate from UI", min_length=1)


@router.post("/{agent_id}/versions/{version}/publish")
def publish_version(agent_id: str, version: int, body: PublishRequest) -> dict:
    """Publish a version (set as active).

    Returns:
        {active_version, version_id, version, author, changelog}.
    """
    try:
        result = get_agent_service().publish_version(agent_id, version, body.reason)
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(404, error_msg) from exc
        # reason too short (should be caught by pydantic, but defensive)
        raise HTTPException(422, error_msg) from exc

    # Schedule webhook if agent has a webhook_url configured
    agent = get_agent_service().resolve_agent(agent_id)
    if agent and agent.webhook_url:
        try:
            schedule_agent_event_webhook(
                webhook_url=agent.webhook_url,
                event="agent.published",
                agent_id=agent_id,
                version=version,
                version_id=result["id"],
                reason=body.reason,
            )
        except Exception:  # pragma: no cover
            logger.exception(
                "failed to schedule agent.published webhook for %s", agent_id
            )

    return {
        "active_version": version,
        "version_id": result.get("id"),
        "version": result.get("version"),
        "author": result.get("author"),
        "changelog": result.get("changelog"),
    }


class DraftRequest(BaseModel):
    author: str = Field(..., min_length=1)


@router.post("/{agent_id}/draft", status_code=201)
def branch_draft(agent_id: str, body: DraftRequest) -> dict:
    """Create a new (non-active) version by cloning the active version.

    Returns:
        {version, version_id, author, changelog}.
    """
    try:
        result = get_agent_service().branch_draft(agent_id, author=body.author)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    return {
        "version": result.get("version"),
        "version_id": result.get("id"),
        "author": result.get("author"),
        "changelog": result.get("changelog"),
    }


class RollbackRequest(BaseModel):
    reason: str = Field(..., min_length=3)
    author: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Runner profile binding
# ---------------------------------------------------------------------------


class SetAgentRunnerProfileBody(BaseModel):
    """Request body for setting an agent's runner profile."""

    runner_profile_id: str


@router.get("/{agent_id}/runner-profile")
def get_agent_runner_profile(
    agent_id: str,
    engine_svc: EngineService = Depends(get_engine_service),
) -> RunnerProfile:
    """Get the runner profile bound to an agent."""
    profile = engine_svc.get_agent_runner_profile(agent_id)
    if profile is None:
        raise HTTPException(404, f"no runner profile bound to agent {agent_id!r}")
    return profile


@router.patch("/{agent_id}/runner-profile")
def set_agent_runner_profile(
    agent_id: str,
    body: SetAgentRunnerProfileBody,
    engine_svc: EngineService = Depends(get_engine_service),
) -> RunnerProfile:
    """Bind a runner profile to an agent."""
    try:
        return engine_svc.set_agent_runner_profile(agent_id, body.runner_profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{agent_id}/runner-profile")
def clear_agent_runner_profile(
    agent_id: str,
    engine_svc: EngineService = Depends(get_engine_service),
) -> None:
    """Remove the runner profile binding from an agent."""
    engine_svc.clear_agent_runner_profile(agent_id)


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str) -> None:
    """Soft-delete an agent.

    Marks ``agent_meta.deleted_at`` and clears the active version pointer.
    Version history is retained; the agent is hidden from list endpoints
    and ``get_agent_def`` returns ``None`` so dispatch fails fast.
    """
    result = get_agent_service().soft_delete(agent_id)
    if result is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})


@router.post("/{agent_id}/disable", status_code=200)
def disable_agent(agent_id: str) -> dict:
    """Mark an agent disabled — visible in lists with ``include_disabled``
    but the run dispatcher refuses to invoke it with HTTP 403.
    """
    meta = get_agent_service().disable(agent_id)
    if meta is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})
    return {"agent_id": agent_id, "disabled_at": meta.get("disabled_at")}


@router.post("/{agent_id}/enable", status_code=200)
def enable_agent(agent_id: str) -> dict:
    """Clear the disabled marker. Idempotent — returns 200 even when the
    agent was already enabled."""
    meta = get_agent_service().enable(agent_id)
    if meta is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})
    return {"agent_id": agent_id, "disabled_at": meta.get("disabled_at")}


@router.post("/{agent_id}/versions/{version}/rollback", status_code=201)
def rollback_version(agent_id: str, version: int, body: RollbackRequest) -> dict:
    """Create a new version rolling back to target_version's config (becomes active).

    Returns:
        {version, version_id, active_version, author, changelog}.
    """
    try:
        result = get_agent_service().rollback_to(
            agent_id, version, body.reason, author=body.author
        )
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(404, error_msg) from exc
        # reason too short (should be caught by pydantic, but defensive)
        raise HTTPException(422, error_msg) from exc

    return {
        "version": result.get("version"),
        "version_id": result.get("id"),
        "active_version": result.get("version"),
        "author": result.get("author"),
        "changelog": result.get("changelog"),
    }
