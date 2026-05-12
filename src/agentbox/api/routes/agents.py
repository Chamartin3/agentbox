"""/agents endpoints — list definitions, fetch one, workspace info."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core import workspaces as ws
from agentbox.core.composition import compose_from_source
from agentbox.core.composition.loader import load_bundle_from_bindings
from agentbox.core.composition.sources import FilesystemBundleSource
from agentbox.core.data.manifest import AgentDef
from agentbox.core.data.runner_profiles import RunnerProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _hydrate_from_snapshot(row: dict) -> AgentDef | None:
    """Reconstruct an AgentDef from a version row snapshot."""
    try:
        return AgentDef.from_db_row(row)
    except ValueError:
        return None
    except Exception:
        logger.exception(
            "agents list: snapshot for %r v%s failed validation",
            row.get("agent_id"),
            row.get("version"),
        )
        return None


@router.get("")
def list_agents() -> list[dict]:
    """List agents from the DB (one row per agent_id, latest version).

    DB-as-source-of-truth: every agent that has ever been imported into
    ``agent_versions`` appears here, even when its on-disk bundle is gone
    or the loader can't see it.
    """
    store = get_store()
    loader = get_loader()
    settings = get_settings()

    def _enrich(
        agent: AgentDef, *, updated_at: str | None = None, version: int | None = None
    ) -> dict:
        try:
            workspace_str = str(ws.resolve_path(agent, settings, loader)[0])
        except Exception:
            workspace_str = ""
        data = {
            **agent.model_dump(),
            "resolved_workspace": workspace_str,
        }
        if updated_at is not None:
            data["updated_at"] = updated_at
        if version is not None:
            data["version"] = version
        return data

    latest_rows = store.list_agents_with_latest()
    enriched: list[dict] = []
    seen: set[str] = set()
    for row in latest_rows:
        agent = _hydrate_from_snapshot(row)
        if agent is None:
            continue
        active = store.get_active_version(agent.id)
        active_version = (
            active["version"] if active else row.get("version")
        )
        enriched.append(
            _enrich(
                agent,
                updated_at=row.get("created_at"),
                version=active_version,
            )
        )
        seen.add(agent.id)

    try:
        manifest = loader.load()
    except Exception:
        manifest = None
    if manifest is not None:
        for agent in manifest.agents:
            if agent.id not in seen:
                enriched.append(_enrich(agent))
                seen.add(agent.id)

    return enriched


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict:
    loader = get_loader()
    settings = get_settings()
    store = get_store()
    # DB-as-source-of-truth: reconstruct AgentDef from the latest version
    # row's snapshot. Loader is only consulted if the DB has nothing.
    agent = store.get_agent_def(agent_id) or loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    prompt = ""
    if agent.prompt_path:
        try:
            prompt = agent.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt = ""
    workspace_path, ephemeral = ws.resolve_path(agent, settings, loader)

    # Composed view — render the DB bundle the same way the runner would.
    # Returns the fully assembled system prompt (with references appended)
    # and the user template (with the output_schema instruction block).
    composed_system: str | None = None
    composed_user: str | None = None
    latest_row = store.get_active_version(agent_id) or store.latest_version(agent_id)
    try:
        bundle = load_bundle_from_bindings(
            agent_id=agent_id,
            store=store,
            fallback_path=None,
        )
        result = compose_from_source(bundle.source, variables={}, render=False)
        composed_system = result.system
        composed_user = result.user
    except FileNotFoundError:
        # Bindings have no system slot yet (agent not migrated). Fall back
        # to the on-disk bundle so the Composition tab still shows
        # something useful.
        if agent.composition is not None:
            try:
                src_path = getattr(agent, "source_path", None)
                bundle_path = (
                    (settings.project_root / src_path).parent
                    if src_path
                    else None
                )
                if bundle_path is not None and bundle_path.exists():
                    shared_roots: dict = {}
                    if settings.manifest_path.exists():
                        try:
                            mf = loader.load()
                            shared_roots = {
                                k: (settings.project_root / v).resolve()
                                for k, v in (mf.shared_assets or {}).items()
                            }
                        except Exception:
                            shared_roots = {}
                    fs_source = FilesystemBundleSource(
                        bundle_path=bundle_path,
                        composition=agent.composition.model_dump(mode="json"),
                        shared_roots=shared_roots,
                    )
                    result = compose_from_source(fs_source, variables={}, render=False)
                    composed_system = result.system
                    composed_user = result.user
            except Exception:
                logger.exception(
                    "agents detail: disk-fallback compose failed for %r", agent_id
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
    agent = loader.get(agent_id)
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
    agent = store.get_agent_def(agent_id) or loader.get(agent_id)
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
