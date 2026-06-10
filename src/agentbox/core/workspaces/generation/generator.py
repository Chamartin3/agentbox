"""Generator — renders a WorkenvConfig to disk against a Recipe.

Pure function. No DB. No globals. Writes files and returns a RenderedDir.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

from agentbox.core.workspaces.generation.config import McpRef, WorkenvConfig
from agentbox.core.workspaces.generation.payload import Item, RenderedDir, Role
from agentbox.core.workspaces.generation.recipe import Recipe


def render(
    target_dir: Path,
    config: WorkenvConfig,
    recipe: Recipe,
) -> RenderedDir:
    """Render a ``WorkenvConfig`` to disk against a ``Recipe``.

    Resolves refs in *config* to content, builds a list of :class:`Item`
    objects, then writes each item to the path prescribed by the recipe
    layout.

    Callers may want to call ``config.validate()`` before rendering.
    """
    items = _build_items(config, recipe)
    written: list[Path] = []

    for item in items:
        layout_path = recipe.resolve_layout(item.role, name=item.name)
        if not layout_path:
            continue
        file_path = target_dir / layout_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(item.content, encoding="utf-8")
        written.append(file_path)

    return RenderedDir(target_dir=target_dir, written_paths=written)


def _build_items(config: WorkenvConfig, recipe: Recipe) -> list[Item]:
    items: list[Item] = []

    if recipe.serialization.get("context") == "json":
        items.append(
            _build_json_context(config, recipe)
        )
    else:
        items.append(
            _build_raw_context(config, recipe)
        )

    for agent in config.agents:
        if agent.role == "main":
            continue
        tmpl = recipe.resolve_template("subagent") or _default_subagent_template
        content = string.Template(tmpl).safe_substitute(
            name=agent.id,
            description="",
        )
        items.append(Item(role=Role.subagent, name=agent.id, content=content))

    if config.mcp_servers:
        mcp_data = _build_mcp_json(config.mcp_servers)
        items.append(
            Item(
                role=Role.mcp_config,
                name="mcp",
                content=json.dumps(mcp_data, indent=2) + "\n",
            )
        )

    if config.permissions.data:
        items.append(
            Item(
                role=Role.permissions,
                name="permissions",
                content=json.dumps(
                    {"permissions": config.permissions.data}, indent=2
                )
                + "\n",
            )
        )

    for skill in config.skills:
        items.append(
            Item(
                role=Role.skill,
                name=skill.id,
                content=f"# {skill.id}\n",
            )
        )

    return items


def _build_raw_context(config: WorkenvConfig, recipe: Recipe) -> Item:
    env_doc = _resolve_env_doc(config)
    permissions_text = (
        json.dumps(config.permissions.data, indent=2)
        if config.permissions.data
        else ""
    )
    tmpl = recipe.resolve_template("context") or _default_context_template
    content = string.Template(tmpl).safe_substitute(
        name=config.name,
        description=config.description,
        env_doc=env_doc,
        permissions=permissions_text,
    )
    return Item(role=Role.context, name=config.name, content=content)


def _build_json_context(config: WorkenvConfig, recipe: Recipe) -> Item:
    blob: dict[str, object] = {
        "$schema": "https://opencode.ai/config.json",
        "theme": "dracula",
        "tools": {"skill": True},
        "permission": {"*": "allow"},
    }

    agents: dict[str, object] = {}
    for a in config.agents:
        if a.role == "main":
            agents[a.id] = {"description": ""}
    blob["agent"] = agents

    blob["mcp"] = _build_opencode_mcp_json(config.mcp_servers)

    return Item(role=Role.context, name=config.name, content=json.dumps(blob, indent=2) + "\n")


def _resolve_env_doc(config: WorkenvConfig) -> str:
    if config.env_doc is None:
        return ""
    if isinstance(config.env_doc, str):
        return config.env_doc
    return f"[ref:{config.env_doc.id}]"


def _build_mcp_json(
    servers: list,
) -> dict[str, object]:
    mcp_servers: dict[str, object] = {}
    for srv in servers:
        if isinstance(srv, McpRef):
            entry: dict[str, object] = {}
            url = srv.config.get("url")
            command = srv.config.get("command")
            transport = srv.config.get("transport", "stdio")

            if url:
                entry["type"] = transport
                entry["url"] = url
            elif command:
                entry["command"] = (
                    command if isinstance(command, str) else command
                )
            mcp_servers[srv.name] = entry
    return {"mcpServers": mcp_servers}


def _build_opencode_mcp_json(
    servers: list,
) -> dict[str, object]:
    mcp_servers: dict[str, object] = {}
    for srv in servers:
        if isinstance(srv, McpRef):
            entry: dict[str, object] = {"enabled": True}
            url = srv.config.get("url")
            command = srv.config.get("command")
            transport = srv.config.get("transport", "stdio")

            if url:
                entry["type"] = "remote" if transport == "http" else transport
                entry["url"] = url
            elif command:
                entry["type"] = "local"
                entry["command"] = (
                    command if isinstance(command, str) else command
                )
            mcp_servers[srv.name] = entry
    return mcp_servers


_default_context_template = "# $name\n\n$description\n\n$env_doc"

_default_subagent_template = "---\nname: $name\n---\n\n# $name\n\n$description\n"
