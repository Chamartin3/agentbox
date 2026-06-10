"""Per-workspace runner config generation (Claude / OpenCode).

Uses the engine-agnostic ``core.workspaces.generation`` pipeline:
``load_workenv()`` → ``load_recipe()`` → ``render()``.

No imports from ``core.engines.render`` — those are internal to the
generation submodule and its recipes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbox.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.data import SessionStore
from agentbox.core.workspaces.generation.builders.from_db import load_workenv
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.workspaces.generation.recipe import list_recipes, load_recipe

from .files import _resolve_agent_or_raise, resolve_workspace_path
from .permissions import load_effective_permissions

__all__ = ["generate_configs_by_name", "generate_configs_for_agent"]


def _generate_into(
    workspace_path: Path,
    workspace_id: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict:
    """Build a WorkenvConfig and render it for every available recipe."""
    perms = load_effective_permissions(
        workspace_id,
        store=store,
        settings=settings,
        loader=None,
        mcp_manifest=None,
    )
    config = load_workenv(store, workspace_id, settings=settings, permissions=perms)
    paths: dict[str, str] = {}
    for engine in list_recipes():
        recipe = load_recipe(engine)
        result = render(workspace_path, config, recipe)
        for p in result.written_paths:
            try:
                key = str(p.relative_to(workspace_path))
            except ValueError:
                key = str(p)
            paths[key] = str(p)
    return paths


def generate_configs_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
    mcp_manifest: Any | None = None,
) -> dict:
    ws_path, _project_root = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    paths = _generate_into(ws_path, name, store=store, settings=settings)
    return {
        "workspace": str(ws_path),
        "generated": paths,
    }


def generate_configs_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
    mcp_manifest: Any | None = None,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    workspace_path, _ = ws.resolve_path(agent, settings, store)
    workspace_id = agent.workspace if agent.workspace != "<ephemeral>" else agent_id
    paths = _generate_into(workspace_path, workspace_id, store=store, settings=settings)
    return {
        "workspace": str(workspace_path),
        "generated": paths,
    }
