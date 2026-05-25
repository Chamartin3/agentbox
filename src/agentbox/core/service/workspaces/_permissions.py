"""Runtime workspace permissions overlay and capability artifacts.

Handles the manifest-default <- DB-overlay <- MCP-derived ``allowed_tools``
composition, plus persisting the rendered ``capabilities.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentbox.config import Settings
from agentbox.core.data import SessionStore
from agentbox.core.run.config import ConfigGenerator
from agentbox.core.run.config.constants import READ_PREFIXES

from ._files import resolve_workspace_path

__all__ = [
    "get_permissions",
    "set_permissions",
    "get_workspace_mcp_tools",
    "load_effective_permissions",
]


def _make_generator(
    project_root: Path, store: SessionStore, mcp_manifest: Any | None
) -> ConfigGenerator:
    servers = store.get_project_mcp_servers()
    agentbox_toml = project_root / "agentbox.toml"
    mcp_server_name = servers[0].name if servers else "mcp"
    return ConfigGenerator(
        agentbox_toml=agentbox_toml,
        mcp_manifest=mcp_manifest,
        mcp_server_name=mcp_server_name,
        verbose=True,
    )


def _is_read_tool(tool: str) -> bool:
    return any(tool.startswith(rp) for rp in READ_PREFIXES)


def _load_tool_manifest(
    project_root: Path, mcp_manifest: Any | None
) -> dict[str, list[str]]:
    if mcp_manifest is not None:
        groups = mcp_manifest.groups
        result: dict[str, list[str]] = {}
        for key, tool_names in groups.items():
            _, _, suffix = key.partition(".")
            dot = suffix.find(".")
            if dot == -1:
                result[suffix] = tool_names
            else:
                prefix = suffix[:dot]
                sub = suffix[dot + 1 :]
                group_name = (
                    f"{prefix}.{sub}" if sub in ("read", "write") else prefix
                )
                result[group_name] = result.get(group_name, []) + tool_names
        return result
    manifest_path = project_root / "bin" / "_generated" / "tool_manifest.json"
    if not manifest_path.is_file():
        return {}
    with open(manifest_path) as f:
        return json.load(f)


def _derive_allowed_tools(
    workspace_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    mcp_manifest: Any | None,
) -> list[str]:
    tool_manifest = _load_tool_manifest(settings.project_root, mcp_manifest)
    if not tool_manifest:
        return []
    servers = store.get_project_mcp_servers()
    mcp_server_name = servers[0].name if servers else "mcp"
    claude_prefix = f"mcp__{mcp_server_name}__"
    discovered = {
        mcp_server_name: [t for tools in tool_manifest.values() for t in tools]
    }
    resolved = store.resolve_workspace_mcp(
        workspace_id,
        [{"name": mcp_server_name, "config": {}}],
        discovered_tools=discovered,
    )
    out: list[str] = []
    for srv in resolved.get("servers", []):
        if not srv.get("enabled"):
            continue
        disabled = set(srv.get("disabled_tools") or [])
        for tool in discovered.get(srv["name"], []):
            if tool in disabled:
                continue
            out.append(f"{claude_prefix}{tool}")
    return out


def _apply_allowed_tools(
    workspace_id: str,
    allowed_tools: list[str],
    *,
    store: SessionStore,
    settings: Settings,
    mcp_manifest: Any | None,
) -> None:
    tool_manifest = _load_tool_manifest(settings.project_root, mcp_manifest)
    if not tool_manifest:
        return
    servers = store.get_project_mcp_servers()
    mcp_server_name = servers[0].name if servers else "mcp"
    claude_prefix = f"mcp__{mcp_server_name}__"
    allowed = set(allowed_tools)
    for tools in tool_manifest.values():
        for tool in tools:
            prefixed = f"{claude_prefix}{tool}"
            enabled = prefixed in allowed
            store.set_workspace_mcp_tool_override(
                workspace_id, mcp_server_name, tool, enabled=enabled
            )


def load_effective_permissions(
    name: str | None,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
    mcp_manifest: Any | None = None,
) -> dict:
    """Return effective workspace permissions: manifest defaults <- DB
    overlay <- derived MCP ``allowed_tools``.
    """
    perms: dict = {
        "allowed_tools": [],
        "allowed_builtin_tools": [],
        "files": [],
        "max_tokens": None,
        "allow_file_write": True,
        "allow_network": True,
    }
    if name and loader is not None:
        ws_def = loader.get_workspace(name)
        if ws_def is not None:
            perms["allowed_builtin_tools"] = list(ws_def.allowed_builtin_tools)
            perms["files"] = [f.model_dump() for f in ws_def.files]
            perms["max_tokens"] = ws_def.max_tokens
            perms["allow_file_write"] = ws_def.allow_file_write
            perms["allow_network"] = ws_def.allow_network

    if not name:
        return perms

    overlay = store.get_workspace_runtime_permissions(name)
    if overlay:
        if overlay.get("allowed_builtin_tools") is not None:
            perms["allowed_builtin_tools"] = overlay["allowed_builtin_tools"]
        if overlay.get("files") is not None:
            perms["files"] = overlay["files"]
        if overlay.get("max_tokens") is not None:
            perms["max_tokens"] = overlay["max_tokens"]
        if overlay.get("allow_file_write") is not None:
            perms["allow_file_write"] = bool(overlay["allow_file_write"])
        if overlay.get("allow_network") is not None:
            perms["allow_network"] = bool(overlay["allow_network"])

    perms["allowed_tools"] = _derive_allowed_tools(
        name, store=store, settings=settings, mcp_manifest=mcp_manifest
    )
    return perms


def _write_capabilities_artifact(ws_path: Path, permissions: dict) -> None:
    """Write the derived capabilities.json artifact to disk."""
    perm_dir = ws_path / "permissions"
    perm_dir.mkdir(parents=True, exist_ok=True)
    perm_file = perm_dir / "capabilities.json"
    perm_file.write_text(
        json.dumps(permissions, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_permissions(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
    mcp_manifest: Any | None = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    permissions = load_effective_permissions(
        name,
        store=store,
        settings=settings,
        loader=loader,
        mcp_manifest=mcp_manifest,
    )
    return {
        "workspace": name,
        "path": str(ws_path / "permissions" / "capabilities.json"),
        "permissions": permissions,
    }


def set_permissions(
    name: str,
    permissions: dict,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
    mcp_manifest: Any | None = None,
    sync_cb: Any = None,
) -> dict:
    """Persist overlay, fan allowed_tools out to MCP overrides, rewrite the
    capabilities.json artifact, regenerate runner configs, and optionally
    call ``sync_cb(store, settings, name)`` for env-doc / subagent /
    resource sync. ``sync_cb`` is injected so this module has no
    transport-level dependency.
    """
    ws_path, project_root = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )

    store.set_workspace_runtime_permissions(
        name,
        allowed_builtin_tools=permissions.get("allowed_builtin_tools"),
        files=permissions.get("files"),
        max_tokens=permissions.get("max_tokens"),
        allow_file_write=permissions.get("allow_file_write"),
        allow_network=permissions.get("allow_network"),
    )
    if "allowed_tools" in permissions and permissions["allowed_tools"] is not None:
        _apply_allowed_tools(
            name,
            list(permissions["allowed_tools"]),
            store=store,
            settings=settings,
            mcp_manifest=mcp_manifest,
        )

    effective = load_effective_permissions(
        name,
        store=store,
        settings=settings,
        loader=loader,
        mcp_manifest=mcp_manifest,
    )
    _write_capabilities_artifact(ws_path, effective)

    allowed_tools = set(effective.get("allowed_tools") or [])
    generator = _make_generator(project_root, store, mcp_manifest)
    generated_paths = generator.generate_for_workspace(
        ws_path,
        allowed_tools=allowed_tools if allowed_tools else None,
        allowed_builtin_tools=effective.get("allowed_builtin_tools") or [],
        files=effective.get("files") or [],
        project_root=project_root,
    )

    if sync_cb is not None:
        try:
            sync_cb(store, settings, name)
        except Exception:
            pass

    return {
        "workspace": name,
        "path": str(ws_path / "permissions" / "capabilities.json"),
        "permissions": effective,
        "regenerated": {
            "claude_agents": str(generated_paths["claude_agents"]),
            "claude_settings": str(generated_paths["claude_settings"]),
            "opencode": str(generated_paths["opencode"]),
        },
    }


def get_workspace_mcp_tools(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
    mcp_manifest: Any | None = None,
) -> dict:
    """Return ALL possible MCP tool groups from the global manifest."""
    servers = store.get_project_mcp_servers()
    mcp_server_name = servers[0].name if servers else "mcp"
    claude_prefix = f"mcp__{mcp_server_name}__"
    opencode_prefix = f"{mcp_server_name}_"

    tool_manifest = _load_tool_manifest(settings.project_root, mcp_manifest)
    groups: list[dict] = []
    for group_name, tools in tool_manifest.items():
        claude_tools = [f"{claude_prefix}{t}" for t in tools]
        opencode_tools = [f"{opencode_prefix}{t}" for t in tools]
        groups.append(
            {
                "name": group_name,
                "tools": tools,
                "claude_tools": claude_tools,
                "opencode_tools": opencode_tools,
                "tool_count": len(tools),
                "kind": "read" if all(_is_read_tool(t) for t in tools) else "mixed",
            }
        )

    builtin_tools = [
        "AskUserQuestion",
        "Task",
        "TodoRead",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
    ]

    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    permissions = load_effective_permissions(
        name,
        store=store,
        settings=settings,
        loader=loader,
        mcp_manifest=mcp_manifest,
    )
    allowed = set(permissions.get("allowed_tools", []))
    for g in groups:
        g["active"] = any(t in allowed for t in g["claude_tools"])
        g["fully_active"] = all(t in allowed for t in g["claude_tools"])

    return {
        "workspace": name,
        "mcp_server_name": mcp_server_name,
        "claude_prefix": claude_prefix,
        "opencode_prefix": opencode_prefix,
        "groups": groups,
        "builtin_tools": builtin_tools,
        "total_groups": len(groups),
        "total_tools": sum(g["tool_count"] for g in groups),
    }
