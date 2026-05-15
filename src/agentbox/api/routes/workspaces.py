"""/workspaces endpoints — inspect, create, reset, read/write files, generate configs, permissions, skills."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agentbox.api._pagination import paginate_list
from agentbox.api.deps import get_loader, get_mcp_registry, get_settings, get_store
from agentbox.core import workspaces as ws
from agentbox.core.config_generation import ConfigGenerator
from agentbox.core.config_generation.constants import (
    READ_PREFIXES,
)
from agentbox.core.skills import discover_skills

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _get_loader():
    return get_loader()


def _get_settings():
    return get_settings()


# ---------------------------------------------------------------------------
# List workspaces
# ---------------------------------------------------------------------------


@router.get("")
def list_workspaces(
    paginated: bool = False,
    q: str | None = None,
    sort: str | None = None,
    order: str = "asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict] | dict:
    """Return all named workspaces with assigned agents and summary stats.

    When ``paginated=true`` returns the standard envelope
    ``{items, total, offset, limit, has_more}`` and supports ``q``, ``sort``,
    ``order``. Without the flag returns a plain list for backward compat.
    """
    loader = _get_loader()
    settings = _get_settings()
    store = get_store()
    try:
        manifest = loader.load()
    except Exception:
        manifest = None

    # The `workspaces` table is the canonical registry — single source of
    # truth for "what workspaces exist". Disk/manifest are decorations
    # used to enrich the row, not to invent rows.
    registry = store.list_workspaces()

    ws_root = settings.workspaces_root
    disk_ids: set[str] = set()
    if ws_root.exists():
        disk_ids = {p.name for p in ws_root.iterdir() if p.is_dir() and not p.name.startswith(".")}

    # Agent assignments from the manifest (decoration only).
    workspace_agents: dict[str, list[str]] = {}
    if manifest:
        for a in manifest.agents:
            ws_name = a.workspace or "default"
            workspace_agents.setdefault(ws_name, []).append(a.id)

    # Resource binding counts.
    try:
        resource_counts = store.count_workspace_file_bindings_by_workspace()
    except Exception:
        resource_counts = {}

    result = []
    for ws_row in registry:
        name = ws_row["name"]
        rel_path = ws_row.get("path")
        ws_path = settings.project_root / rel_path if rel_path else ws_root / name
        agents = workspace_agents.get(name, [])

        file_count = 0
        skill_count = 0
        if ws_path.exists():
            for p in ws_path.rglob("*"):
                if p.is_file() and _is_user_file(str(p.relative_to(ws_path))):
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

    if paginated:
        return paginate_list(
            result,
            q=q,
            q_fields=("name", "description", "path"),
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )
    return result


# ---------------------------------------------------------------------------
# Create / delete (registry-level)
# ---------------------------------------------------------------------------


class CreateWorkspaceBody(BaseModel):
    name: str
    description: str | None = None
    path: str | None = None


@router.post("", status_code=201)
def create_workspace_registry(body: CreateWorkspaceBody) -> dict:
    """Create a new workspace in the canonical registry.

    The workspace exists in the registry immediately; the on-disk
    directory is materialized lazily by the executor on first use.
    """
    store = get_store()
    try:
        row = store.create_workspace(
            body.name,
            description=body.description,
            path=body.path,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return row


@router.delete("/by-name/{name}", status_code=200)
def delete_workspace_registry(name: str, purge_disk: bool = False) -> dict:
    """Remove a workspace from the registry and cascade-delete every
    satellite row (env-docs, MCP overrides, file bindings, etc.).

    Optionally purges the on-disk workspace directory as well
    (``?purge_disk=true``). The directory is left alone by default —
    deleting registry state shouldn't clobber user files.
    """
    store = get_store()
    settings = _get_settings()
    existing = store.get_workspace(name)
    if existing is None:
        raise HTTPException(404, f"unknown workspace {name!r}")
    counts = store.delete_workspace_cascade(name)
    disk_removed = False
    if purge_disk:
        ws_path = settings.project_root / existing["path"] if existing.get("path") else (
            settings.workspaces_root / name
        )
        if ws_path.exists() and ws_path.is_dir():
            shutil.rmtree(ws_path)
            disk_removed = True
    return {"deleted": name, "counts": counts, "disk_removed": disk_removed}


# ---------------------------------------------------------------------------
# Workspace by name
# ---------------------------------------------------------------------------


def _resolve_workspace(name: str) -> tuple[Path, Path]:
    """Return (workspace_path, project_root) for a named workspace.

    Registry-first: the canonical `workspaces` table is the source of
    truth for existence. The manifest is consulted only to enrich the
    path when the registry row has no explicit ``path`` and a manifest
    entry happens to declare one.
    """
    settings = _get_settings()
    store = get_store()
    row = store.get_workspace(name)
    if row is None:
        raise HTTPException(404, f"unknown workspace {name!r}")
    rel_path = row.get("path")
    if not rel_path:
        loader = _get_loader()
        w = loader.get_workspace(name)
        if w is not None and w.path:
            rel_path = w.path
    ws_path = (
        settings.project_root / rel_path if rel_path else settings.workspaces_root / name
    )
    return ws_path, settings.project_root


def _make_generator(project_root: Path, loader) -> ConfigGenerator:
    """Build a ConfigGenerator from the manifest."""
    manifest = loader.load()
    agentbox_toml = project_root / "agentbox.toml"
    mcp_server_name = manifest.mcp_servers[0].name if manifest.mcp_servers else "mcp"
    return ConfigGenerator(
        agentbox_toml=agentbox_toml,
        mcp_manifest=_try_get_mcp_manifest(),
        mcp_server_name=mcp_server_name,
        verbose=True,
    )


def _try_get_mcp_manifest():
    try:
        return get_mcp_registry().manifest
    except Exception:
        return None


_FILE_HIDE_PREFIXES = (
    ".agentbox/",
    ".claude/",
    ".opencode/",
    "permissions/",
    "skills/",
)

# Root-level files that are render artifacts (re-materialized every run by the
# executor / env-doc renderer / config generator). They have dedicated UI
# surfaces, so excluding them from the Files list avoids confusing users into
# editing files that will be silently overwritten.
_RENDERED_ARTIFACT_FILES = frozenset({
    "CLAUDE.md",
    "AGENTS.md",
})


def _is_user_file(rel_path: str) -> bool:
    """User files are anything outside generated/permissions/skill dirs and
    not a render artifact at the workspace root.
    """
    if rel_path in _RENDERED_ARTIFACT_FILES:
        return False
    return not any(
        rel_path == p.rstrip("/") or rel_path.startswith(p) for p in _FILE_HIDE_PREFIXES
    )


@router.get("/by-name/{name}")
def get_workspace_by_name(name: str) -> dict:
    ws_path, _ = _resolve_workspace(name)
    files: list[dict] = []
    if ws_path.exists():
        for p in sorted(ws_path.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(ws_path))
                if not _is_user_file(rel):
                    continue
                files.append(
                    {
                        "path": rel,
                        "size": p.stat().st_size,
                    }
                )
    return {
        "name": name,
        "path": str(ws_path),
        "exists": ws_path.exists(),
        "files": files,
        "generated_configs": {},
    }


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def _load_permissions(ws_path: Path, name: str | None = None) -> dict:
    """Return effective workspace permissions: manifest defaults <- DB overlay
    <- derived MCP ``allowed_tools``.

    capabilities.json is no longer the source of truth — it is a derived
    artifact written by ``generate_for_workspace`` on save. The legacy file
    on disk is ignored.
    """
    loader = _get_loader()

    # Defaults from WorkspaceDef (manifest).
    perms: dict = {
        "allowed_tools": [],
        "allowed_builtin_tools": [],
        "files": [],
        "max_tokens": None,
        "allow_file_write": True,
        "allow_network": True,
    }
    if name:
        ws_def = loader.get_workspace(name)
        if ws_def is not None:
            perms["allowed_builtin_tools"] = list(ws_def.allowed_builtin_tools)
            perms["files"] = [f.model_dump() for f in ws_def.files]
            perms["max_tokens"] = ws_def.max_tokens
            perms["allow_file_write"] = ws_def.allow_file_write
            perms["allow_network"] = ws_def.allow_network

    if not name:
        return perms

    # Overlay DB row (only set fields override).
    store = get_store()
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

    # Derive allowed_tools from MCP overrides + tool manifest.
    perms["allowed_tools"] = _derive_allowed_tools(name)
    return perms


def _derive_allowed_tools(workspace_id: str) -> list[str]:
    """Flatten the workspace's effective MCP state into prefixed tool names.

    Walks the tool manifest, applies workspace MCP server enable + per-tool
    overrides + policy, and returns the Claude-prefixed names the runner
    expects. Returns ``[]`` when no MCP manifest is loaded.
    """
    settings = _get_settings()
    loader = _get_loader()
    tool_manifest = _load_tool_manifest(settings.project_root)
    if not tool_manifest:
        return []
    try:
        manifest = loader.load()
    except Exception:
        return []
    mcp_server_name = manifest.mcp_servers[0].name if manifest.mcp_servers else "mcp"
    claude_prefix = f"mcp__{mcp_server_name}__"

    store = get_store()
    discovered = {mcp_server_name: [t for tools in tool_manifest.values() for t in tools]}
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


def _apply_allowed_tools(workspace_id: str, allowed_tools: list[str]) -> None:
    """Translate a full ``allowed_tools`` list into per-MCP-tool DB overrides.

    Full-replace semantics: tools present become enabled overrides, tools
    absent become disabled overrides. Only acts on tools known to the
    current tool manifest — unknown prefixed names are ignored.
    """
    settings = _get_settings()
    loader = _get_loader()
    tool_manifest = _load_tool_manifest(settings.project_root)
    if not tool_manifest:
        return
    try:
        manifest = loader.load()
    except Exception:
        return
    mcp_server_name = manifest.mcp_servers[0].name if manifest.mcp_servers else "mcp"
    claude_prefix = f"mcp__{mcp_server_name}__"
    allowed = set(allowed_tools)
    store = get_store()
    for tools in tool_manifest.values():
        for tool in tools:
            prefixed = f"{claude_prefix}{tool}"
            enabled = prefixed in allowed
            store.set_workspace_mcp_tool_override(
                workspace_id, mcp_server_name, tool, enabled=enabled
            )


def _write_capabilities_artifact(ws_path: Path, permissions: dict) -> None:
    """Write the derived capabilities.json artifact to disk.

    Kept so existing runtime consumers and CLI fallbacks (executor's
    ``_load_workspace_permissions``, ``load_capabilities``) still see the
    effective permissions. Not the source of truth — overwritten on every
    save and on every config-generation run.
    """
    perm_dir = ws_path / "permissions"
    perm_dir.mkdir(parents=True, exist_ok=True)
    perm_file = perm_dir / "capabilities.json"
    perm_file.write_text(
        json.dumps(permissions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


@router.get("/by-name/{name}/permissions")
def get_permissions_by_name(name: str) -> dict:
    ws_path, _ = _resolve_workspace(name)
    permissions = _load_permissions(ws_path, name)
    return {
        "workspace": name,
        "path": str(ws_path / "permissions" / "capabilities.json"),
        "permissions": permissions,
    }


class PermissionsBody(BaseModel):
    permissions: dict


@router.put("/by-name/{name}/permissions")
def set_permissions_by_name(name: str, body: PermissionsBody) -> dict:
    """Write workspace permissions to DB and regenerate disk artifacts.

    Source of truth split:
      - ``allowed_tools`` (MCP-prefixed) → fanned out to
        ``workspace_mcp_tool_overrides`` (full-replace semantics).
      - everything else → ``workspace_runtime_permissions`` overlay.

    capabilities.json is rewritten as a derived artifact for the executor
    fallback path; it is not read by ``GET /permissions``.
    """
    loader = _get_loader()
    store = get_store()
    ws_path, project_root = _resolve_workspace(name)

    p = body.permissions
    # Persist overlay fields (None means "clear override, inherit manifest").
    store.set_workspace_runtime_permissions(
        name,
        allowed_builtin_tools=p.get("allowed_builtin_tools"),
        files=p.get("files"),
        max_tokens=p.get("max_tokens"),
        allow_file_write=p.get("allow_file_write"),
        allow_network=p.get("allow_network"),
    )
    # Fan allowed_tools out to per-MCP-tool overrides.
    if "allowed_tools" in p and p["allowed_tools"] is not None:
        _apply_allowed_tools(name, list(p["allowed_tools"]))

    # Re-derive the effective view and write the artifact + runner configs.
    effective = _load_permissions(ws_path, name)
    _write_capabilities_artifact(ws_path, effective)

    allowed_tools = set(effective.get("allowed_tools") or [])
    generator = _make_generator(project_root, loader)
    generated_paths = generator.generate_for_workspace(
        ws_path,
        allowed_tools=allowed_tools if allowed_tools else None,
        allowed_builtin_tools=effective.get("allowed_builtin_tools") or [],
        files=effective.get("files") or [],
        project_root=project_root,
    )

    # Phase 1: also re-sync env-doc / subagents / resource bindings so
    # the workspace's on-disk state matches what the saved permissions
    # imply. Best-effort; failures are logged inside.
    try:
        from agentbox.api.deps import get_settings as _get_settings
        from agentbox.core.workspace_sync import sync_workspace_by_name

        sync_workspace_by_name(store, _get_settings(), name)
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


# ---------------------------------------------------------------------------
# MCP tool groups — ALL possible groups from global manifest
# ---------------------------------------------------------------------------


def _load_tool_manifest(project_root: Path) -> dict[str, list[str]]:
    mcp_manifest = _try_get_mcp_manifest()
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
                group_name = f"{prefix}.{sub}" if sub in ("read", "write") else prefix
                result[group_name] = result.get(group_name, []) + tool_names
        return result
    manifest_path = project_root / "bin" / "_generated" / "tool_manifest.json"
    if not manifest_path.is_file():
        return {}
    with open(manifest_path) as f:
        return json.load(f)


def _is_read_tool(tool: str) -> bool:
    """Check if a raw tool name (without prefix) is a read operation."""
    return any(tool.startswith(rp) for rp in READ_PREFIXES)


@router.get("/by-name/{name}/mcp-tools")
def get_workspace_mcp_tools(name: str) -> dict:
    """Return ALL possible MCP tool groups from the global manifest.

    This lists every tool group defined in the system, not just those
    currently assigned to agents in the workspace. The UI uses this to
    let users toggle permissions for any available capability.
    """
    loader = _get_loader()
    settings = _get_settings()
    manifest = loader.load()

    # Determine MCP server name from manifest.
    mcp_server_name = manifest.mcp_servers[0].name if manifest.mcp_servers else "mcp"
    claude_prefix = f"mcp__{mcp_server_name}__"
    opencode_prefix = f"{mcp_server_name}_"

    # Load global manifest (all possible tool groups)
    tool_manifest = _load_tool_manifest(settings.project_root)

    # Build groups with full tool names for both runners
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

    # Also include built-in tools that are always available
    builtin_tools = [
        "AskUserQuestion",
        "Task",
        "TodoRead",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
    ]

    # Current workspace permissions (to show which are already enabled)
    ws_path, _ = _resolve_workspace(name)
    permissions = _load_permissions(ws_path, name)
    allowed = set(permissions.get("allowed_tools", []))

    # Mark which groups are currently active
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


@router.post("/by-name/{name}/generate-configs")
def generate_configs_by_name(name: str) -> dict:
    loader = _get_loader()
    ws_path, project_root = _resolve_workspace(name)

    # Read workspace permissions and respect them when generating.
    permissions = _load_permissions(ws_path, name)
    allowed_tools = set(permissions.get("allowed_tools", []))
    allowed_builtin_tools = permissions.get("allowed_builtin_tools") or []
    files = permissions.get("files") or []

    generator = _make_generator(project_root, loader)
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
# Skills generation (.claude/skills/ and .opencode/skills/)
# ---------------------------------------------------------------------------


def _generate_claude_skills(skills: list, ws_path: Path) -> Path:
    """Generate .claude/skills/ directory with skill descriptors."""
    claude_dir = ws_path / ".claude" / "skills"
    if claude_dir.exists():
        shutil.rmtree(claude_dir)
    claude_dir.mkdir(parents=True, exist_ok=True)

    for skill in skills:
        skill_dir = claude_dir / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill.content, encoding="utf-8")

    return claude_dir


def _generate_opencode_skills(skills: list, ws_path: Path) -> Path:
    """Generate .opencode/skills/ directory with skill descriptors."""
    opencode_dir = ws_path / ".opencode" / "skills"
    if opencode_dir.exists():
        shutil.rmtree(opencode_dir)
    opencode_dir.mkdir(parents=True, exist_ok=True)

    for skill in skills:
        skill_dir = opencode_dir / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill.content, encoding="utf-8")

    return opencode_dir


@router.post("/by-name/{name}/generate-skills")
def generate_skills_by_name(name: str) -> dict:
    ws_path, _ = _resolve_workspace(name)
    skills = discover_skills(ws_path)

    claude_dir = _generate_claude_skills(skills, ws_path)
    opencode_dir = _generate_opencode_skills(skills, ws_path)

    return {
        "workspace": name,
        "skills_count": len(skills),
        "generated": {
            "claude_skills": str(claude_dir),
            "opencode_skills": str(opencode_dir),
        },
    }


# ---------------------------------------------------------------------------
# Skills by workspace name
# ---------------------------------------------------------------------------


@router.get("/by-name/{name}/skills")
def list_skills_by_name(name: str) -> dict:
    ws_path, _ = _resolve_workspace(name)
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


@router.get("/by-name/{name}/skills/{skill_name}")
def get_skill_content_by_name(name: str, skill_name: str) -> dict:
    from agentbox.core.skills import find_skill

    ws_path, _ = _resolve_workspace(name)
    skill_md = find_skill(ws_path, skill_name)
    if skill_md is None:
        raise HTTPException(404, f"skill {skill_name!r} not found")
    return {
        "workspace": name,
        "skill": skill_name,
        "path": str(skill_md.relative_to(ws_path)),
        "content": skill_md.read_text(encoding="utf-8"),
    }


# ---------------------------------------------------------------------------
# Files by workspace name
# ---------------------------------------------------------------------------


class FileBody(BaseModel):
    path: str
    content: str


@router.get("/by-name/{name}/file")
def read_file_by_name(name: str, path: str) -> dict:
    ws_path, _ = _resolve_workspace(name)
    target = (ws_path / path).resolve()
    if not str(target).startswith(str(ws_path.resolve())):
        raise HTTPException(400, "path escapes workspace")
    if not target.is_file():
        raise HTTPException(404, "no such file")
    return {"path": path, "content": target.read_text(encoding="utf-8")}


@router.put("/by-name/{name}/file")
def write_file_by_name(name: str, body: FileBody) -> dict:
    ws_path, _ = _resolve_workspace(name)
    target = (ws_path / body.path).resolve()
    if not str(target).startswith(str(ws_path.resolve())):
        raise HTTPException(400, "path escapes workspace")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    return {"path": body.path, "bytes": len(body.content)}


# ---------------------------------------------------------------------------
# Legacy agent-centric endpoints (kept for backward compat)
# ---------------------------------------------------------------------------


@router.get("/{agent_id}")
def get_workspace(agent_id: str) -> dict:
    loader = _get_loader()
    settings = _get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404, f"unknown agent {agent_id!r}")
    w = ws.info(agent, settings, loader)
    files: list[dict] = []
    if w.exists:
        for p in sorted(w.path.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(w.path))
                if not _is_user_file(rel):
                    continue
                files.append({"path": rel, "size": p.stat().st_size})
    return {
        "agent_id": w.agent_id,
        "path": str(w.path),
        "exists": w.exists,
        "ephemeral": w.ephemeral,
        "files": files,
        "generated_configs": {},
    }


@router.post("/{agent_id}")
def create_workspace(agent_id: str) -> dict:
    loader = _get_loader()
    settings = _get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    path = ws.ensure(agent, settings, loader, scaffold=True)
    return {"path": str(path)}


@router.delete("/{agent_id}")
def reset_workspace(agent_id: str) -> dict:
    loader = _get_loader()
    settings = _get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    path = ws.reset(agent, settings, loader)
    return {"path": str(path)}


@router.post("/{agent_id}/generate-configs")
def generate_configs(agent_id: str) -> dict:
    loader = _get_loader()
    settings = _get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    workspace_path, _ = ws.resolve_path(agent, settings, loader)
    permissions = _load_permissions(workspace_path, agent.workspace)
    generator = _make_generator(settings.project_root, loader)
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


@router.get("/{agent_id}/skills")
def list_skills(agent_id: str) -> dict:
    loader = _get_loader()
    settings = _get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    workspace_path, _ = ws.resolve_path(agent, settings, loader)
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


@router.get("/{agent_id}/file")
def read_file(agent_id: str, path: str) -> dict:
    loader = _get_loader()
    settings = _get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    ws_path, _ = ws.resolve_path(agent, settings, loader)
    target = (ws_path / path).resolve()
    if not str(target).startswith(str(ws_path.resolve())):
        raise HTTPException(400, "path escapes workspace")
    if not target.is_file():
        raise HTTPException(404, "no such file")
    return {"path": path, "content": target.read_text(encoding="utf-8")}


@router.put("/{agent_id}/file")
def write_file(agent_id: str, body: FileBody) -> dict:
    loader = _get_loader()
    settings = _get_settings()
    agent = loader.get(agent_id)
    if agent is None:
        raise HTTPException(404)
    ws_path = ws.ensure(agent, settings, loader, scaffold=False)
    target = (ws_path / body.path).resolve()
    if not str(target).startswith(str(ws_path.resolve())):
        raise HTTPException(400, "path escapes workspace")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    return {"path": body.path, "bytes": len(body.content)}
