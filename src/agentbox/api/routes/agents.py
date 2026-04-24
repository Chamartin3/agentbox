"""/agents endpoints — list definitions, fetch one, workspace info."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core import workspaces as ws

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents() -> list[dict]:
    loader = get_loader()
    settings = get_settings()
    agents = loader.load().agents
    # Include resolved workspace info for each agent
    return [
        {
            **a.model_dump(),
            "resolved_workspace": str(ws.resolve_path(a, settings, loader)[0]),
        }
        for a in agents
    ]


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict:
    loader = get_loader()
    settings = get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    prompt = ""
    if agent.prompt_path:
        try:
            prompt = agent.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt = ""
    workspace_path, ephemeral = ws.resolve_path(agent, settings, loader)

    store = get_store()
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
    latest = store.latest_version(agent_id)

    return {
        "agent": agent.model_dump(),
        "prompt": prompt,
        "workspace": {
            "path": str(workspace_path),
            "ephemeral": ephemeral,
            "generated_configs": {},
        },
        "current_version": latest["version"] if latest else None,
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
