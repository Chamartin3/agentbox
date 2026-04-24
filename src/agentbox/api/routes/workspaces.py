"""/workspaces endpoints — inspect, create, reset, read/write files, generate configs, permissions, skills."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_loader, get_mcp_registry, get_settings
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
def list_workspaces() -> list[dict]:
    """Return all named workspaces with assigned agents and summary stats."""
    loader = _get_loader()
    settings = _get_settings()
    manifest = loader.load()

    # Build a map of workspace name -> list of agent IDs
    workspace_agents: dict[str, list[str]] = {}
    for a in manifest.agents:
        ws_name = a.workspace or "default"
        workspace_agents.setdefault(ws_name, []).append(a.id)

    result = []
    for w in manifest.workspaces:
        ws_path = settings.project_root / w.path
        agents = workspace_agents.get(w.name, [])

        # Count user-visible files (exclude .claude/, .opencode/, etc.) and skills
        file_count = 0
        skill_count = 0
        if ws_path.exists():
            for p in ws_path.rglob("*"):
                if p.is_file() and _is_user_file(str(p.relative_to(ws_path))):
                    file_count += 1
            skill_count = len(discover_skills(ws_path))

        result.append({
            "name": w.name,
            "path": str(ws_path),
            "description": w.description,
            "kind": "named",
            "agents": agents,
            "agent_count": len(agents),
            "file_count": file_count,
            "skill_count": skill_count,
            "exists": ws_path.exists(),
        })

    return result


# ---------------------------------------------------------------------------
# Workspace by name
# ---------------------------------------------------------------------------


def _resolve_workspace(name: str) -> tuple[Path, Path]:
    """Return (workspace_path, project_root) for a named workspace."""
    loader = _get_loader()
    settings = _get_settings()
    w = loader.get_workspace(name)
    if w is None:
        raise HTTPException(404, f"unknown workspace {name!r}")
    return settings.project_root / w.path, settings.project_root


def _make_generator(project_root: Path, loader) -> ConfigGenerator:
    """Build a ConfigGenerator from the manifest."""
    manifest = loader.load()
    agentbox_toml = project_root / "agentbox.toml"
    mcp_server_name = (
        manifest.mcp_servers[0].name if manifest.mcp_servers else "mcp"
    )
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


_FILE_HIDE_PREFIXES = (".agentbox/", ".claude/", ".opencode/", "permissions/", "skills/")


def _is_user_file(rel_path: str) -> bool:
    """User files are anything outside generated/permissions/skill dirs.

    Generated configs, capabilities.json, and skill packs each have their
    own UI section, so excluding them from the Files list avoids noise.
    """
    return not any(rel_path == p.rstrip("/") or rel_path.startswith(p) for p in _FILE_HIDE_PREFIXES)


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
                files.append({
                    "path": rel,
                    "size": p.stat().st_size,
                })
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


def _load_permissions(ws_path: Path) -> dict:
    """Load capabilities.json from workspace permissions directory."""
    perm_file = ws_path / "permissions" / "capabilities.json"
    if perm_file.is_file():
        return json.loads(perm_file.read_text(encoding="utf-8"))
    return {
        "allowed_tools": [],
        "allowed_builtin_tools": [],
        "files": [],
        "max_tokens": 64000,
        "allow_file_write": False,
        "allow_network": False,
    }


def _save_permissions(ws_path: Path, permissions: dict) -> None:
    """Save capabilities.json to workspace permissions directory."""
    perm_dir = ws_path / "permissions"
    perm_dir.mkdir(parents=True, exist_ok=True)
    perm_file = perm_dir / "capabilities.json"
    perm_file.write_text(json.dumps(permissions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@router.get("/by-name/{name}/permissions")
def get_permissions_by_name(name: str) -> dict:
    ws_path, _ = _resolve_workspace(name)
    permissions = _load_permissions(ws_path)
    return {
        "workspace": name,
        "path": str(ws_path / "permissions" / "capabilities.json"),
        "permissions": permissions,
    }


class PermissionsBody(BaseModel):
    permissions: dict


@router.put("/by-name/{name}/permissions")
def set_permissions_by_name(name: str, body: PermissionsBody) -> dict:
    loader = _get_loader()
    ws_path, project_root = _resolve_workspace(name)
    _save_permissions(ws_path, body.permissions)

    # Regenerate both Claude and OpenCode configs from the same permission spec.
    # The workspace permissions are the single source of truth.
    allowed_tools = set(body.permissions.get("allowed_tools", []))
    allowed_builtin_tools = body.permissions.get("allowed_builtin_tools") or []
    files = body.permissions.get("files") or []
    generator = _make_generator(project_root, loader)
    generated_paths = generator.generate_for_workspace(
        ws_path,
        allowed_tools=allowed_tools if allowed_tools else None,
        allowed_builtin_tools=allowed_builtin_tools,
        files=files,
        project_root=project_root,
    )

    return {
        "workspace": name,
        "path": str(ws_path / "permissions" / "capabilities.json"),
        "permissions": body.permissions,
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
    mcp_server_name = (
        manifest.mcp_servers[0].name if manifest.mcp_servers else "mcp"
    )
    claude_prefix = f"mcp__{mcp_server_name}__"
    opencode_prefix = f"{mcp_server_name}_"

    # Load global manifest (all possible tool groups)
    tool_manifest = _load_tool_manifest(settings.project_root)

    # Build groups with full tool names for both runners
    groups: list[dict] = []
    for group_name, tools in tool_manifest.items():
        claude_tools = [f"{claude_prefix}{t}" for t in tools]
        opencode_tools = [f"{opencode_prefix}{t}" for t in tools]
        groups.append({
            "name": group_name,
            "tools": tools,
            "claude_tools": claude_tools,
            "opencode_tools": opencode_tools,
            "tool_count": len(tools),
            "kind": "read" if all(_is_read_tool(t) for t in tools) else "mixed",
        })

    # Also include built-in tools that are always available
    builtin_tools = ["AskUserQuestion", "Task", "TodoRead", "TodoWrite", "WebFetch", "WebSearch"]

    # Current workspace permissions (to show which are already enabled)
    ws_path, _ = _resolve_workspace(name)
    permissions = _load_permissions(ws_path)
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
    permissions = _load_permissions(ws_path)
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
    permissions = _load_permissions(workspace_path)
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
