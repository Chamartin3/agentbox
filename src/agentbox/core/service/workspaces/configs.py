"""Per-workspace runner config generation (Claude / OpenCode).

Uses the engine-agnostic ``core.workspaces.generation`` pipeline:
``load_workenv()`` → ``load_recipe()`` → ``render()``.

Also provides a ``generate_legacy_runner_configs`` wrapper around the
legacy ``ConfigGenerator`` (engine_config/) for CLI tools and diagnostics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbox.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.data import SessionStore
from agentbox.core.workspaces.generation.builders.from_db import load_workenv
from agentbox.core.workspaces.generation.engine_config import (
    ConfigGenerator,
    make_generator,
)
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.workspaces.generation.recipe import list_recipes, load_recipe

from .files import _resolve_agent_or_raise, resolve_workspace_path
from .permissions import load_effective_permissions

__all__ = [
    "generate_configs_by_name",
    "generate_configs_for_agent",
    "generate_legacy_runner_configs",
]


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


def generate_legacy_runner_configs(
    target_dir: Path,
    *,
    store: SessionStore,
    settings: Settings,
    mcp_registry: Any = None,
    servers: list[dict] | None = None,
    allowed_builtin_tools: list[str] | None = None,
    files: list[dict] | None = None,
    project_root: Path | None = None,
) -> dict[str, Path]:
    """Generate legacy runner configs (claude_agents.json, claude_mcp.json,
    opencode.json, etc.) into *target_dir* using the engine_config generator.

    Wraps ``make_generator()`` so callers (CLI, diagnostics) do not import
    ``workspaces.generation.engine_config`` directly.  When *servers* is
    provided (workspace-filtered MCP overrides), the wrapper builds a
    ``ConfigGenerator`` with those servers instead of the global list.
    """
    if servers is not None:
        # Workspace-specific MCP overrides: build a ConfigGenerator
        # with the filtered server list instead of the global one.
        mcp_manifest = getattr(mcp_registry, "manifest", None) if mcp_registry else None
        mcp_specs = store.get_project_mcp_servers()
        mcp_spec = mcp_specs[0] if mcp_specs else None
        generator = ConfigGenerator(
            agentbox_toml=settings.project_root / "agentbox.toml",
            mcp_manifest=mcp_manifest,
            mcp_server_name=mcp_spec.name if mcp_spec else "mcp",
            mcp_command=mcp_spec.command if mcp_spec and mcp_spec.command else ["mcp_serve.sh"],
            mcp_url=mcp_spec.url if mcp_spec else None,
            mcp_transport=str(mcp_spec.transport) if mcp_spec else "http",
            servers=servers,
            verbose=False,
        )
    else:
        generator = make_generator(
            settings=settings,
            store=store,
            mcp_registry=mcp_registry,
        )
    return generator.generate_configs_into(
        target_dir,
        allowed_builtin_tools=allowed_builtin_tools,
        files=files,
        project_root=project_root,
    )


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
