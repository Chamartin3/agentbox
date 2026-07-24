"""DB-only write endpoints under /api/agents."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.config import load_settings
from agentbox.core.service.agents import AgentServiceError
from agentbox.core.workspaces.tooling.mcp.registry import McpRegistry

logger = logging.getLogger(__name__)


class _PatchAgentResult(TypedDict):
    """Response shape of PATCH /api/agents/{agent_id}."""

    agent: dict
    pruned_tools: list[str]  # grants revoked because the workspace changed

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _make_catalog_resolver(ctx: APIContext) -> Callable[[str], set[str]]:
    """Return a resolver that lists callable names installed in a workspace.

    Built at the API layer where both AgentService and WorkspaceService are
    legitimately available, so the resolver can be injected into
    ``patch_agent_config`` without creating a forbidden
    ``service.agents -> service.workspaces`` import edge.
    """

    def resolve(workspace: str) -> set[str]:
        registry = McpRegistry(load_settings().mcp_cache_dir)
        registry.hydrate_from_cache()
        return {
            c.name
            for c in ctx.workspaces.installed_callables(workspace, mcp_registry=registry)
        }

    return resolve


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
def patch_agent(
    agent_id: str,
    body: AgentPatch,
    ctx: APIContext = Depends(get_api_context),
) -> _PatchAgentResult:
    """DB-first config save. Creates a new ``agent_versions`` row.

    On-disk files are not written by this endpoint — use
    ``POST /api/agents/{id}/export`` for that.
    """
    patch = body.model_dump(exclude_unset=True)
    try:
        updated, pruned_tools = ctx.agents.patch_agent_config(
            agent_id, patch, catalog_resolver=_make_catalog_resolver(ctx)
        )
    except AgentServiceError as exc:
        detail: object = (
            exc.detail if exc.code == "empty_patch" else {"code": exc.code, "detail": exc.detail}
        )
        raise HTTPException(exc.status_code, detail) from exc
    return {"agent": updated.model_dump(), "pruned_tools": pruned_tools}
