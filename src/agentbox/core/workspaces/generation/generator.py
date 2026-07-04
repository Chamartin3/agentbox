"""Generator — renders a WorkenvConfig to disk against a Recipe.

Pure function. No DB. No globals. Writes files and returns a RenderedDir.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

from agentbox.core.workspaces.generation._paths import safe_dest
from agentbox.core.workspaces.generation.config import McpRef, ResourceRef, WorkenvConfig
from agentbox.core.workspaces.generation.payload import Item, RenderedDir, Role
from agentbox.core.workspaces.generation.recipe import Recipe


def render(
    target_dir: Path,
    config: WorkenvConfig,
    recipe: Recipe,
    *,
    system_prompt: str | None = None,
    extra_items: list[Item] | None = None,
) -> RenderedDir:
    """Render a ``WorkenvConfig`` to disk against a ``Recipe``.

    Builds a list of :class:`Item` objects, then writes each to the path
    the recipe layout prescribes. Engine-specific config blobs (e.g.
    opencode.json) are passed by the caller via *extra_items* — the
    backend's ``build_workspace_items`` is invoked at the call site, not
    here, so ``generator`` stays independent of the backend registry.

    When ``system_prompt`` is provided, it replaces the env-doc baseline
    as the content for the ``context`` role item (CLAUDE.md / AGENTS.md).

    Callers may want to call ``config.validate()`` before rendering.
    """
    items = _build_items(config, recipe, system_prompt=system_prompt)
    if extra_items:
        items += extra_items

    written: list[Path] = []
    for item in items:
        layout_path = recipe.resolve_layout(item.role, name=item.name)
        if not layout_path:
            continue
        file_path = safe_dest(target_dir, layout_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(item.content, encoding="utf-8")
        written.append(file_path)

    return RenderedDir(target_dir=target_dir, written_paths=written)


def _build_items(
    config: WorkenvConfig,
    recipe: Recipe,
    *,
    system_prompt: str | None = None,
) -> list[Item]:
    items: list[Item] = []

    # Env-doc body → the engine's instruction file (CLAUDE.md / AGENTS.md).
    # Plain text, identical for every engine; the recipe owns the filename.
    # When a per-run system_prompt is provided, it replaces the env-doc baseline.
    if recipe.layout.get("context"):
        items.append(_build_context(config, recipe, system_prompt=system_prompt))

    # Subagents render from the recipe's subagent template. Engines whose
    # format can't be expressed as a text template (e.g. Codex's escaped
    # TOML) ship no template and emit subagents via their backend
    # build_workspace_items hook instead, so skip them here.
    subagent_tmpl = recipe.resolve_template("subagent")
    if subagent_tmpl is not None:
        for agent in config.agents:
            if agent.role == "main":
                continue
            content = string.Template(subagent_tmpl).safe_substitute(
                name=agent.id,
                description=agent.description,
                prompt=agent.prompt,
            )
            items.append(
                Item(role=Role.subagent, name=agent.id, content=content)
            )

    if config.mcp_servers:
        items.append(
            Item(
                role=Role.mcp_config,
                name="mcp",
                content=json.dumps(_build_mcp_json(config.mcp_servers), indent=2)
                + "\n",
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

    # Skills are resource-backed: the materializer is the single writer of
    # their real blob body (per-engine layout from each recipe). The generator
    # deliberately emits no skill stub — a stub would be a second, empty writer.

    return items


def _build_context(
    config: WorkenvConfig,
    recipe: Recipe,
    *,
    system_prompt: str | None = None,
) -> Item:
    tmpl = recipe.resolve_template("context") or _default_context_template
    env_content = system_prompt if system_prompt is not None else _resolve_env_doc(config)
    content = string.Template(tmpl).safe_substitute(env_doc=env_content)
    return Item(role=Role.context, name=config.name, content=content)


def _resolve_env_doc(config: WorkenvConfig) -> str:
    if isinstance(config.env_doc, str):
        return config.env_doc
    if isinstance(config.env_doc, ResourceRef):
        return f"[ref:{config.env_doc.id}]"
    return ""


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
                entry["command"] = command
            mcp_servers[srv.name] = entry
    return {"mcpServers": mcp_servers}


_default_context_template = "$env_doc"
