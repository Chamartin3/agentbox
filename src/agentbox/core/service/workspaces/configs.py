"""Per-workspace runner config generation (Claude / OpenCode).

Uses the engine-agnostic ``core.workspaces.generation`` pipeline:
``load_workenv()`` → ``load_recipe()`` → ``render()``.

Also owns interactive-launch config placement (``launch_runner_configs``):
the engine discovers config natively from its cwd, so this service renders
into the workspace without ever clobbering the user's own files, and
removes exactly what it created on exit.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.db import SessionStore
from agentbox.core.service.system.service import SystemService
from agentbox.core.workspaces.generation.builders.from_db import load_workenv
from agentbox.core.workspaces.generation.config import McpRef, WorkenvConfig
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.workspaces.generation.recipe import list_recipes, load_recipe

from .files import _resolve_agent_or_raise, resolve_workspace_path
from .permissions import load_effective_permissions

__all__ = [
    "generate_configs_by_name",
    "generate_configs_for_agent",
    "launch_runner_configs",
]


def _project_mcp_refs(store: SessionStore, servers: list[dict] | None) -> list[McpRef]:
    """Build ``McpRef``s from project (or override) MCP servers."""
    specs = servers if servers is not None else SystemService().get_project_mcp_servers()
    refs: list[McpRef] = []
    for s in specs:
        name = s["name"] if isinstance(s, dict) else s.name
        if isinstance(s, dict):
            cfg = {k: v for k, v in s.items() if k != "name"}
        else:
            cfg = {
                k: v
                for k, v in {
                    "url": s.url,
                    "command": s.command,
                    "transport": str(s.transport) if s.transport else None,
                }.items()
                if v is not None
            }
        refs.append(McpRef(name=name, config=cfg))
    return refs


@contextlib.contextmanager
def launch_runner_configs(
    workspace_path: Path,
    *,
    store: SessionStore,
    settings: Settings,
    servers: list[dict] | None = None,
    keep: bool = False,
) -> Iterator[Path]:
    """Place native runner config in *workspace_path* for an interactive launch.

    The engine (Claude / OpenCode) discovers its config from the cwd, so the
    files have to live in the workspace — but a persistent workspace may hold
    the user's own ``.mcp.json`` / ``.claude`` / ``opencode.json``. This
    renders into a temp dir first and copies in only files that don't already
    exist, then removes exactly those on exit (unless *keep*). Never
    overwrites or deletes a user file. Yields *workspace_path*.
    """
    config = WorkenvConfig(
        name="project", mcp_servers=_project_mcp_refs(store, servers)
    )
    created: list[Path] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        rels: set[str] = set()
        for engine in list_recipes():
            for p in render(tmp_dir, config, load_recipe(engine)).written_paths:
                rels.add(str(p.relative_to(tmp_dir)))
        for rel in rels:
            dst = workspace_path / rel
            if dst.exists():
                continue  # never clobber the user's own config
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp_dir / rel, dst)
            created.append(dst)
    try:
        yield workspace_path
    finally:
        if not keep:
            for p in created:
                with contextlib.suppress(OSError):
                    p.unlink()


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
    mcp_manifest: Any | None = None,
) -> dict:
    ws_path, _project_root = resolve_workspace_path(
        name, store=store, settings=settings
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
    mcp_manifest: Any | None = None,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, store=store)
    workspace_path, _ = ws.resolve_path(agent, settings, store)
    workspace_id = (
        agent.workspace
        if agent.workspace and agent.workspace != "<ephemeral>"
        else agent_id
    )
    paths = _generate_into(workspace_path, workspace_id, store=store, settings=settings)
    return {
        "workspace": str(workspace_path),
        "generated": paths,
    }
