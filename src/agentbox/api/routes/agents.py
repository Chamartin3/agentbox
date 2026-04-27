"""/agents endpoints — list definitions, fetch one, workspace info."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core import workspaces as ws
from agentbox.core.composition import compose_from_source
from agentbox.core.composition.sources import DbBundleSource
from agentbox.core.data.manifest import AgentDef

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _hydrate_from_snapshot(row: dict) -> AgentDef | None:
    """Reconstruct an AgentDef from a version row's content_snapshot."""
    snap = row.get("content_snapshot")
    if not snap:
        return None
    try:
        data = json.loads(snap)
    except json.JSONDecodeError:
        logger.warning(
            "agents list: snapshot for %r v%s is not valid JSON",
            row.get("agent_id"),
            row.get("version"),
        )
        return None
    try:
        return AgentDef.model_validate(data)
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

    latest_rows = store.list_agents_with_latest()
    enriched: list[dict] = []
    for row in latest_rows:
        agent = _hydrate_from_snapshot(row)
        if agent is None:
            continue
        try:
            workspace_str = str(ws.resolve_path(agent, settings, loader)[0])
        except Exception:
            workspace_str = ""
        enriched.append(
            {
                **agent.model_dump(),
                "resolved_workspace": workspace_str,
                "updated_at": row.get("created_at"),
                "version": row.get("version"),
            }
        )
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
    bundle_files: list[dict] = []
    latest_row = store.latest_version(agent_id)
    if latest_row is not None and agent.composition is not None:
        try:
            files = store.list_version_files(latest_row["id"])
            if files:
                bundle_files = [
                    {
                        "kind": f["kind"],
                        "relative_path": f["relative_path"],
                        "sha256": f["sha256"],
                        "source_uri": f.get("source_uri"),
                    }
                    for f in files
                ]
                source = DbBundleSource(
                    composition=agent.composition.model_dump(mode="json"),
                    files=list(files),
                )
                result = compose_from_source(source, variables={}, render=False)
                composed_system = result.system
                composed_user = result.user
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
        "bundle_files": bundle_files,
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
