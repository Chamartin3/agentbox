"""/agents endpoints — list definitions, fetch one, workspace info."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core import workspaces as ws
from agentbox.core.data.manifest import AgentDef
from agentbox.core.data.runner_profiles import RunnerProfile
from agentbox.core.data.schema import agent_runner_profiles
from agentbox.core.data.schema import runs as runs_table
from agentbox.core.prompt.composition import compose_from_source
from agentbox.core.prompt.composition.loader import load_bundle_from_bindings
from agentbox.core.service.agents import list_all_agents, resolve_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents() -> list[dict]:
    """List agents from the DB (one row per agent_id, latest version).

    DB-as-source-of-truth: every agent that has ever been imported into
    ``agent_versions`` appears here, even when its on-disk bundle is gone
    or the loader can't see it. Resolution lives in
    ``core.services.agents.list_all_agents`` so the MCP surface returns
    the exact same set.
    """
    store = get_store()
    loader = get_loader()
    settings = get_settings()

    # Per-agent run counts and bound runner profiles, in two cheap queries.
    run_counts: dict[str, int] = {}
    last_run_at: dict[str, str] = {}
    profile_bindings: dict[str, str] = {}
    try:
        with store.engine.connect() as conn:
            for agent_id, n, last in conn.execute(
                select(
                    runs_table.c.agent_id,
                    func.count().label("n"),
                    func.max(runs_table.c.created_at).label("last"),
                ).group_by(runs_table.c.agent_id)
            ):
                if agent_id:
                    run_counts[agent_id] = int(n)
                    if last:
                        last_run_at[agent_id] = str(last)
            for agent_id, profile_id in conn.execute(
                select(
                    agent_runner_profiles.c.agent_id,
                    agent_runner_profiles.c.runner_profile_id,
                )
            ):
                profile_bindings[agent_id] = profile_id
    except Exception:
        logger.exception("agents list: failed to load run counts / profile bindings")

    def _enrich(agent: AgentDef) -> dict:
        try:
            workspace_str = str(ws.resolve_path(agent, settings, store)[0])
        except Exception:
            workspace_str = ""
        active = store.get_active_version(agent.id)
        latest = store.latest_version(agent.id)
        data = {
            **agent.model_dump(),
            "resolved_workspace": workspace_str,
            "run_count": run_counts.get(agent.id, 0),
            "last_run_at": last_run_at.get(agent.id),
            "runner_profile_id": profile_bindings.get(agent.id),
        }
        if latest is not None:
            data["updated_at"] = latest.get("created_at")
            data["version"] = (
                active["version"] if active else latest.get("version")
            )
        data["last_activity_at"] = max(
            (t for t in (data.get("updated_at"), data.get("last_run_at")) if t),
            default=None,
        )
        return data

    return [_enrich(agent) for agent in list_all_agents(store=store, loader=loader)]


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict:
    loader = get_loader()
    settings = get_settings()
    store = get_store()
    # Shared resolver — DB first, manifest fallback. Same call MCP makes.
    agent = resolve_agent(agent_id, store=store, loader=loader)
    if agent is None:
        raise HTTPException(404)
    workspace_path, ephemeral = ws.resolve_path(agent, settings, store)

    # Composed view — render the DB bundle the same way the runner would.
    # Returns the fully assembled system prompt (with references appended)
    # and the user template (with the output_schema instruction block).
    composed_system: str | None = None
    composed_user: str | None = None
    latest_row = store.get_active_version(agent_id) or store.latest_version(agent_id)
    # DB is source of truth — surface the active version's prompt_content;
    # only fall back to the on-disk prompt_path file when the DB row has no
    # stored content (legacy / unmigrated agents).
    prompt = ""
    db_prompt = (latest_row or {}).get("prompt_content")
    if isinstance(db_prompt, str) and db_prompt:
        prompt = db_prompt
    elif agent.prompt_path:
        try:
            prompt = agent.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt = ""
    try:
        bundle = load_bundle_from_bindings(
            agent_id=agent_id,
            store=store,
        )
        result = compose_from_source(bundle.source, variables={}, render=False)
        composed_system = result.system
        composed_user = result.user
    except FileNotFoundError:
        logger.info(
            "agents detail: no system slot binding for %r; preview empty",
            agent_id,
        )
    except Exception:
        logger.exception(
            "agents detail: composition preview failed for %r", agent_id
        )

    versions = store.list_versions(agent_id)
    enriched = []
    for v in versions:
        comments = store.list_comments(v["id"])
        rating = store.get_rating(v["id"])
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
                "config_json": v.get("config_json"),
            }
        )
    return {
        "agent": agent.model_dump(),
        "prompt": prompt,
        "composed_system": composed_system,
        "composed_user": composed_user,
        "workspace": {
            "path": str(workspace_path),
            "ephemeral": ephemeral,
            "generated_configs": {},
        },
        "current_version": latest_row["version"] if latest_row else None,
        "versions": enriched,
    }


# ---------------------------------------------------------------------------
# Workspace assignment
# ---------------------------------------------------------------------------


class WorkspaceBody(BaseModel):
    workspace: str | None = None


@router.patch("/{agent_id}/workspace")
def set_workspace(agent_id: str, body: WorkspaceBody) -> dict:
    """Update an agent's workspace assignment in agentbox.toml.

    This edits the TOML file on disk. Requires the agent to be declared
    inline (``[[agents]]`` block), not directory-discovered.
    """
    # For v1, we return what the workspace *would* be.
    # Editing agentbox.toml programmatically is fragile; the UI can
    # display the effective workspace and guide the user to edit the file.
    loader = get_loader()
    store = get_store()
    agent = resolve_agent(agent_id, store=store, loader=loader)
    if agent is None:
        raise HTTPException(404)
    # TODO: implement TOML editing via tomlkit
    return {
        "agent_id": agent_id,
        "workspace": body.workspace,
        "note": "Edit agentbox.toml manually to persist workspace changes",
    }


# ---------------------------------------------------------------------------
# Lifecycle — publish, branch draft, rollback
# ---------------------------------------------------------------------------


class PublishRequest(BaseModel):
    reason: str = Field(default="activate from UI", min_length=1)


@router.post("/{agent_id}/versions/{version}/publish")
def publish_version(agent_id: str, version: int, body: PublishRequest) -> dict:
    """Publish a draft version (flip is_draft, set as active).

    Returns:
        {active_version, version_id, is_draft, version, author, changelog}.
    """
    store = get_store()
    loader = get_loader()
    try:
        result = store.publish_version(agent_id, version, body.reason)
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(404, error_msg) from exc
        # reason too short (should be caught by pydantic, but defensive)
        raise HTTPException(422, error_msg) from exc

    # Schedule webhook if agent has a webhook_url configured
    agent = resolve_agent(agent_id, store=store, loader=loader)
    if agent and agent.webhook_url:
        from agentbox.api.webhooks import schedule_agent_event_webhook

        try:
            schedule_agent_event_webhook(
                webhook_url=agent.webhook_url,
                event="agent.published",
                agent_id=agent_id,
                version=version,
                version_id=result.get("id"),
                reason=body.reason,
            )
        except Exception:  # pragma: no cover
            logger.exception(
                "failed to schedule agent.published webhook for %s", agent_id
            )

    return {
        "active_version": version,
        "version_id": result.get("id"),
        "is_draft": result.get("is_draft", False),
        "version": result.get("version"),
        "author": result.get("author"),
        "changelog": result.get("changelog"),
    }


class DraftRequest(BaseModel):
    author: str = Field(..., min_length=1)


@router.post("/{agent_id}/draft", status_code=201)
def branch_draft(agent_id: str, body: DraftRequest) -> dict:
    """Create a new draft version by cloning the active version.

    Returns:
        {version, version_id, is_draft, author, changelog}.
    """
    store = get_store()
    try:
        result = store.branch_draft(agent_id, author=body.author)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    return {
        "version": result.get("version"),
        "version_id": result.get("id"),
        "is_draft": result.get("is_draft", True),
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
) -> RunnerProfile:
    """Get the runner profile bound to an agent."""
    store = get_store()
    profile = store.get_agent_runner_profile(agent_id)
    if profile is None:
        raise HTTPException(
            404, f"no runner profile bound to agent {agent_id!r}"
        )
    return profile


@router.patch("/{agent_id}/runner-profile")
def set_agent_runner_profile(
    agent_id: str,
    body: SetAgentRunnerProfileBody,
) -> RunnerProfile:
    """Bind a runner profile to an agent."""
    store = get_store()
    profile = store.get_runner_profile(body.runner_profile_id)
    if profile is None:
        raise HTTPException(
            404, f"runner profile not found: {body.runner_profile_id!r}"
        )
    return store.set_agent_runner_profile(agent_id, body.runner_profile_id)


@router.delete("/{agent_id}/runner-profile")
def clear_agent_runner_profile(
    agent_id: str,
) -> None:
    """Remove the runner profile binding from an agent."""
    store = get_store()
    store.clear_agent_runner_profile(agent_id)


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str) -> None:
    """Soft-delete an agent.

    Marks ``agent_meta.deleted_at`` and clears the active version pointer.
    Version history is retained; the agent is hidden from list endpoints
    and ``get_agent_def`` returns ``None`` so dispatch fails fast.
    """
    store = get_store()
    result = store.soft_delete_agent(agent_id)
    if result is None:
        raise HTTPException(404, {"code": "unknown_agent", "detail": agent_id})


@router.post("/{agent_id}/versions/{version}/rollback", status_code=201)
def rollback_version(agent_id: str, version: int, body: RollbackRequest) -> dict:
    """Create a new version rolling back to target_version's config (becomes active).

    Returns:
        {version, version_id, is_draft, active_version, author, changelog}.
    """
    store = get_store()
    try:
        result = store.rollback_to(agent_id, version, body.reason, author=body.author)
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(404, error_msg) from exc
        # reason too short (should be caught by pydantic, but defensive)
        raise HTTPException(422, error_msg) from exc

    return {
        "version": result.get("version"),
        "version_id": result.get("id"),
        "is_draft": result.get("is_draft", False),
        "active_version": result.get("version"),
        "author": result.get("author"),
        "changelog": result.get("changelog"),
    }
