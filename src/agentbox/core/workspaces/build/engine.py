"""Generator — renders a WorkspaceConfig to disk against a Recipe.

Pure function. No DB. No globals. Writes files and returns a RenderedDir.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

from agentbox.core.workspaces.build._paths import safe_dest
from agentbox.core.mcp.launch import resolve_mcp_launch_command
from agentbox.core.data.workenv import McpRef, ResourceRef, WorkspaceConfig
from agentbox.core.data.workenv import Item, RenderedDir, Role, WrittenItem
from agentbox.core.data.workenv import Recipe


def _write_item(target_dir: Path, item: Item, recipe: Recipe) -> WrittenItem | None:
    """Write one item to its recipe-resolved path; return its metadata.

    Returns None when the recipe declares no layout for the item's role.
    """
    layout_path = recipe.resolve_layout(item.role, name=item.name)
    if not layout_path:
        return None
    file_path = safe_dest(target_dir, layout_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(item.content, encoding="utf-8")
    return WrittenItem(
        role=item.role.value, file=layout_path, bytes=len(item.content.encode())
    )


def render(
    target_dir: Path,
    config: WorkspaceConfig,
    recipe: Recipe,
    *,
    system_prompt: str | None = None,
    extra_items: list[Item] | None = None,
) -> RenderedDir:
    """Render a ``WorkspaceConfig`` to disk against a ``Recipe``.

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
    rendered: list[WrittenItem] = []
    for item in items:
        wi = _write_item(target_dir, item, recipe)
        if wi is None:
            continue
        written.append(safe_dest(target_dir, wi.file))
        rendered.append(wi)

    return RenderedDir(target_dir=target_dir, written_paths=written, items=rendered)


def render_context_only(
    target_dir: Path, config: WorkspaceConfig, recipes: list[Recipe]
) -> list[WrittenItem]:
    """Write ONLY the instruction/context file (CLAUDE.md / AGENTS.md) for each
    recipe — the env-doc preview path. Same writer + templating as ``render``,
    no mcp/permissions/subagent items.
    """
    out: list[WrittenItem] = []
    for recipe in recipes:
        if not recipe.layout.get("context"):
            continue
        wi = _write_item(target_dir, _build_context(config, recipe), recipe)
        if wi is not None:
            out.append(wi)
    return out


def _build_items(
    config: WorkspaceConfig,
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
    config: WorkspaceConfig,
    recipe: Recipe,
    *,
    system_prompt: str | None = None,
) -> Item:
    tmpl = recipe.resolve_template("context") or _default_context_template
    env_content = system_prompt if system_prompt is not None else _resolve_env_doc(config)
    content = string.Template(tmpl).safe_substitute(env_doc=env_content)
    return Item(role=Role.context, name=config.name, content=content)


def _resolve_env_doc(config: WorkspaceConfig) -> str:
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
                # Resolve through the shared launcher so the config-file
                # path and the token in-process path launch the same binary.
                launched = resolve_mcp_launch_command(list(command))
                entry["command"] = launched["command"]
                if launched["args"]:
                    entry["args"] = launched["args"]

            # Per-server tool scoping: when the workspace has disabled specific
            # tools on this server, emit the claude_code-native `tools.exclude`
            # block so the .mcp.json consumer never sees those tools.
            if srv.disabled_tools:
                entry["tools"] = {"exclude": sorted(srv.disabled_tools)}

            mcp_servers[srv.name] = entry
    return {"mcpServers": mcp_servers}


_default_context_template = "$env_doc"
