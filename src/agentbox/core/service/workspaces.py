"""Service layer for workspace orchestration.

Wraps the registry CRUD, on-disk file ops, permission overlay,
MCP-derived tool resolution, config generation, and skill discovery
that used to live in ``api/routes/workspaces.py``. Routes become a
thin transport adapter: parse → call → map domain errors to HTTP.

Dependency injection is explicit (``store``, ``settings``, ``loader``,
``mcp_manifest``) so this module has no import of FastAPI deps. That
lets MCP tools and the CLI consume the same use-cases.

Domain errors raised here:

* :class:`WorkspaceNotFound` — unknown registry name.
* :class:`WorkspaceExists` — create called for a name that's already
  registered (registry uniqueness violation).
* :class:`WorkspacePathEscape` — file ops where the resolved path
  walks above the workspace root.
* :class:`AgentNotFound` — re-exported from
  :mod:`core.service.prompts` for the legacy agent-centric endpoints.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core import workspaces as ws
from agentbox.core.resource.skills import discover_skills, find_skill
from agentbox.core.run.config import ConfigGenerator
from agentbox.core.run.config.constants import READ_PREFIXES
from agentbox.core.service.prompts import AgentNotFound

if TYPE_CHECKING:
    from agentbox.config import Settings
    from agentbox.core.data import SessionStore

__all__ = [
    "AgentNotFound",
    "WorkspaceNotFound",
    "WorkspaceExists",
    "WorkspacePathEscape",
    # Registry
    "list_workspaces_enriched",
    "create_workspace_registry",
    "delete_workspace_registry",
    "get_workspace_by_name",
    # Permissions / MCP / configs
    "get_permissions",
    "set_permissions",
    "get_workspace_mcp_tools",
    "generate_configs_by_name",
    # Skills
    "generate_skills_by_name",
    "list_skills_by_name",
    "get_skill_content_by_name",
    # Files
    "read_file_by_name",
    "write_file_by_name",
    # Legacy agent-centric
    "get_workspace_for_agent",
    "create_workspace_for_agent",
    "reset_workspace_for_agent",
    "generate_configs_for_agent",
    "list_skills_for_agent",
    "read_file_for_agent",
    "write_file_for_agent",
    # Helpers
    "resolve_workspace_path",
    "is_user_file",
]


class WorkspaceNotFound(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"unknown workspace {name!r}")
        self.name = name


class WorkspaceExists(ValueError):
    def __init__(self, name: str, detail: str | None = None) -> None:
        super().__init__(detail or f"workspace {name!r} already exists")
        self.name = name


class WorkspacePathEscape(ValueError):
    def __init__(self, path: str) -> None:
        super().__init__("path escapes workspace")
        self.path = path


# ---------------------------------------------------------------------------
# Constants / file filters
# ---------------------------------------------------------------------------


_FILE_HIDE_PREFIXES = (
    ".agentbox/",
    ".claude/",
    ".opencode/",
    "permissions/",
    "skills/",
)

_RENDERED_ARTIFACT_FILES = frozenset({"CLAUDE.md", "AGENTS.md"})


def is_user_file(rel_path: str) -> bool:
    """User files are anything outside generated/permissions/skill dirs and
    not a render artifact at the workspace root.
    """
    if rel_path in _RENDERED_ARTIFACT_FILES:
        return False
    return not any(
        rel_path == p.rstrip("/") or rel_path.startswith(p)
        for p in _FILE_HIDE_PREFIXES
    )


def _is_read_tool(tool: str) -> bool:
    return any(tool.startswith(rp) for rp in READ_PREFIXES)


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def resolve_workspace_path(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> tuple[Path, Path]:
    """Return ``(workspace_path, project_root)`` for a named workspace.

    Registry-first: the canonical ``workspaces`` table is the source of
    truth for existence. The manifest loader is consulted only to
    enrich the path when the registry row has no explicit ``path``.
    Raises :class:`WorkspaceNotFound` when the name is unknown.
    """
    row = store.get_workspace(name)
    if row is None:
        raise WorkspaceNotFound(name)
    rel_path = row.get("path")
    if not rel_path and loader is not None:
        w = loader.get_workspace(name)
        if w is not None and getattr(w, "path", None):
            rel_path = w.path
    ws_path = (
        settings.project_root / rel_path
        if rel_path
        else settings.workspaces_root / name
    )
    return ws_path, settings.project_root


def _safe_resolve(ws_path: Path, rel: str) -> Path:
    target = (ws_path / rel).resolve()
    if not str(target).startswith(str(ws_path.resolve())):
        raise WorkspacePathEscape(rel)
    return target


# ---------------------------------------------------------------------------
# Tool manifest / generator
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Registry CRUD + listing
# ---------------------------------------------------------------------------


def list_workspaces_enriched(
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> list[dict]:
    """Return all named workspaces with agent assignments + summary stats."""
    try:
        manifest = loader.load() if loader is not None else None
    except Exception:
        manifest = None

    registry = store.list_workspaces()
    ws_root = settings.workspaces_root
    disk_ids: set[str] = set()
    if ws_root.exists():
        disk_ids = {
            p.name
            for p in ws_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        }

    workspace_agents: dict[str, list[str]] = {}
    if manifest:
        for a in manifest.agents:
            ws_name = a.workspace or "default"
            workspace_agents.setdefault(ws_name, []).append(a.id)

    try:
        resource_counts = store.count_workspace_file_bindings_by_workspace()
    except Exception:
        resource_counts = {}

    result: list[dict] = []
    for ws_row in registry:
        name = ws_row["name"]
        rel_path = ws_row.get("path")
        ws_path = (
            settings.project_root / rel_path
            if rel_path
            else ws_root / name
        )
        agents = workspace_agents.get(name, [])
        file_count = 0
        skill_count = 0
        if ws_path.exists():
            for p in ws_path.rglob("*"):
                if p.is_file() and is_user_file(str(p.relative_to(ws_path))):
                    file_count += 1
            skill_count = len(discover_skills(ws_path))
        result.append(
            {
                "name": name,
                "path": str(ws_path),
                "description": ws_row.get("description"),
                "source": ws_row.get("source"),
                "kind": "named",
                "agents": agents,
                "agent_count": len(agents),
                "file_count": file_count,
                "skill_count": skill_count,
                "resource_count": resource_counts.get(name, 0),
                "exists": ws_path.exists(),
                "on_disk": name in disk_ids,
                "created_at": ws_row.get("created_at"),
                "updated_at": ws_row.get("updated_at"),
            }
        )
    return result


def create_workspace_registry(
    name: str,
    *,
    store: SessionStore,
    description: str | None = None,
    path: str | None = None,
) -> dict:
    try:
        return store.create_workspace(name, description=description, path=path)
    except ValueError as exc:
        raise WorkspaceExists(name, str(exc)) from exc


def delete_workspace_registry(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    purge_disk: bool = False,
) -> dict:
    existing = store.get_workspace(name)
    if existing is None:
        raise WorkspaceNotFound(name)
    counts = store.delete_workspace_cascade(name)
    disk_removed = False
    if purge_disk:
        ws_path = (
            settings.project_root / existing["path"]
            if existing.get("path")
            else (settings.workspaces_root / name)
        )
        if ws_path.exists() and ws_path.is_dir():
            shutil.rmtree(ws_path)
            disk_removed = True
    return {"deleted": name, "counts": counts, "disk_removed": disk_removed}


def get_workspace_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    files: list[dict] = []
    if ws_path.exists():
        for p in sorted(ws_path.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(ws_path))
                if not is_user_file(rel):
                    continue
                files.append({"path": rel, "size": p.stat().st_size})
    return {
        "name": name,
        "path": str(ws_path),
        "exists": ws_path.exists(),
        "files": files,
        "generated_configs": {},
    }


# ---------------------------------------------------------------------------
# Permissions endpoints
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def generate_configs_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
    mcp_manifest: Any | None = None,
) -> dict:
    ws_path, project_root = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    permissions = load_effective_permissions(
        name,
        store=store,
        settings=settings,
        loader=loader,
        mcp_manifest=mcp_manifest,
    )
    allowed_tools = set(permissions.get("allowed_tools", []))
    allowed_builtin_tools = permissions.get("allowed_builtin_tools") or []
    files = permissions.get("files") or []

    generator = _make_generator(project_root, store, mcp_manifest)
    paths = generator.generate_for_workspace(
        ws_path,
        allowed_tools=allowed_tools if allowed_tools else None,
        allowed_builtin_tools=allowed_builtin_tools,
        files=files,
        project_root=project_root,
    )
    return {
        "workspace": str(ws_path),
        "generated": {k: str(v) for k, v in paths.items()},
    }


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def _generate_skills_dir(skills: list, ws_path: Path, subdir: str) -> Path:
    out_dir = ws_path / subdir / "skills"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        skill_dir = out_dir / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill.content, encoding="utf-8")
    return out_dir


def generate_skills_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    skills = discover_skills(ws_path)
    claude_dir = _generate_skills_dir(skills, ws_path, ".claude")
    opencode_dir = _generate_skills_dir(skills, ws_path, ".opencode")
    return {
        "workspace": name,
        "skills_count": len(skills),
        "generated": {
            "claude_skills": str(claude_dir),
            "opencode_skills": str(opencode_dir),
        },
    }


def list_skills_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    skills = discover_skills(ws_path)
    return {
        "workspace": name,
        "workspace_path": str(ws_path),
        "skills": [
            {
                "name": s.name,
                "path": str(s.path.relative_to(ws_path)),
                "size": len(s.content.encode("utf-8")),
            }
            for s in skills
        ],
    }


def get_skill_content_by_name(
    name: str,
    skill_name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict | None:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    skill_md = find_skill(ws_path, skill_name)
    if skill_md is None:
        return None
    return {
        "workspace": name,
        "skill": skill_name,
        "path": str(skill_md.relative_to(ws_path)),
        "content": skill_md.read_text(encoding="utf-8"),
    }


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def read_file_by_name(
    name: str,
    path: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict | None:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    target = _safe_resolve(ws_path, path)
    if not target.is_file():
        return None
    return {"path": path, "content": target.read_text(encoding="utf-8")}


def write_file_by_name(
    name: str,
    path: str,
    content: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    target = _safe_resolve(ws_path, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "bytes": len(content)}


# ---------------------------------------------------------------------------
# Legacy agent-centric endpoints
# ---------------------------------------------------------------------------


def _resolve_agent_or_raise(agent_id: str, *, loader: Any):
    agent = loader.get(agent_id) if loader is not None else None
    if agent is None:
        raise AgentNotFound(agent_id)
    return agent


def get_workspace_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    info = ws.info(agent, settings, loader)
    files: list[dict] = []
    if info.exists:
        for p in sorted(info.path.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(info.path))
                if not is_user_file(rel):
                    continue
                files.append({"path": rel, "size": p.stat().st_size})
    return {
        "agent_id": info.agent_id,
        "path": str(info.path),
        "exists": info.exists,
        "ephemeral": info.ephemeral,
        "files": files,
        "generated_configs": {},
    }


def create_workspace_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    path = ws.ensure(agent, settings, store, scaffold=True)
    return {"path": str(path)}


def reset_workspace_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    path = ws.reset(agent, settings, store)
    return {"path": str(path)}


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
    permissions = load_effective_permissions(
        agent.workspace,
        store=store,
        settings=settings,
        loader=loader,
        mcp_manifest=mcp_manifest,
    )
    generator = _make_generator(settings.project_root, store, mcp_manifest)
    paths = generator.generate_for_workspace(
        workspace_path,
        allowed_builtin_tools=permissions.get("allowed_builtin_tools") or [],
        files=permissions.get("files") or [],
        project_root=settings.project_root,
    )
    return {
        "workspace": str(workspace_path),
        "generated": {k: str(v) for k, v in paths.items()},
    }


def list_skills_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    workspace_path, _ = ws.resolve_path(agent, settings, store)
    skills = discover_skills(workspace_path)
    return {
        "agent_id": agent_id,
        "workspace": str(workspace_path),
        "skills": [
            {
                "name": s.name,
                "path": str(s.path.relative_to(workspace_path)),
                "size": len(s.content.encode("utf-8")),
            }
            for s in skills
        ],
    }


def read_file_for_agent(
    agent_id: str,
    path: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
) -> dict | None:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    ws_path, _ = ws.resolve_path(agent, settings, store)
    target = _safe_resolve(ws_path, path)
    if not target.is_file():
        return None
    return {"path": path, "content": target.read_text(encoding="utf-8")}


def write_file_for_agent(
    agent_id: str,
    path: str,
    content: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    ws_path = ws.ensure(agent, settings, store, scaffold=False)
    target = _safe_resolve(ws_path, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "bytes": len(content)}


# ---------------------------------------------------------------------------
# Workspace MCP overlay
# ---------------------------------------------------------------------------


def _manifest_servers(store: SessionStore) -> list[dict]:
    """Project-manifest MCP servers projected as ``{name, config}`` dicts.

    Returns ``[]`` when no manifest is loaded — callers see the "no
    manifest" case explicitly rather than via an exception.
    """
    servers = store.get_project_mcp_servers()
    if not servers:
        return []
    return [{"name": s.name, "config": s.model_dump(exclude={"name"})} for s in servers]


def resolve_workspace_mcp(workspace_id: str, *, store: SessionStore) -> dict:
    """Effective per-workspace MCP servers — union of manifest + overrides."""
    return store.resolve_workspace_mcp(workspace_id, _manifest_servers(store))


def refresh_workspace_mcp_discovery(
    workspace_id: str, *, store: SessionStore
) -> dict:
    """Invalidate the MCP tool discovery cache for this workspace's servers.

    Returns ``{invalidated: N}`` — number of cache entries removed.
    """
    resolved = store.resolve_workspace_mcp(workspace_id, _manifest_servers(store))
    removed = 0
    for s in resolved.get("servers", []):
        removed += store.invalidate_server_cache(s["name"])
    return {"invalidated": removed}
