"""Generate Claude Code and OpenCode configurations from agent definitions.

Ported from bin/generate_configs.py. Generates per-workspace configs
that are consumed by the runners at execution time.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

from .constants import (
    CLAUDE_MCP_PREFIX,
    CLAUDE_TO_OPENCODE_TOOLS,
    DENIED_BUILTIN_TOOLS,
    DISABLED_OPENCODE_AGENTS,
    OPENCODE_MCP_PREFIX,
    OPENCODE_SCHEMA,
    OPENCODE_THEME,
    READ_PREFIXES,
)
from .discovery import AgentDiscovery, DiscoveredAgent

Permission = Literal["allow", "ask"]


def _is_read_tool_claude(tool: str, prefix: str = CLAUDE_MCP_PREFIX) -> bool:
    if not tool.startswith(prefix):
        return False
    suffix = tool[len(prefix) :]
    if any(suffix.startswith(rp) for rp in READ_PREFIXES):
        return True
    parts = suffix.split("_", 1)
    return len(parts) == 2 and any(parts[1].startswith(rp) for rp in READ_PREFIXES)


def build_claude_agents(agents: list[DiscoveredAgent]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for agent in agents:
        result[agent["name"]] = {
            "description": agent["description"],
            "prompt": agent["prompt"],
            "allowedTools": agent["mcp_tools"],
        }
    return result


def _materialize_workspace_files(
    workspace_path: Path,
    files: list[dict],
    project_root: Path,
) -> int:
    """Copy declared host paths into the workspace cwd.

    Each entry is ``{src, dst}`` where ``src`` is resolved relative to
    ``project_root`` and ``dst`` is relative to ``workspace_path``.
    Existing destinations are removed first so the copy stays in sync
    with the source. Symlinks pointing outside the workspace are not
    supported (docker bind mounts cannot follow them).
    """
    count = 0
    for entry in files:
        if not isinstance(entry, dict):
            continue
        src_rel = entry.get("src")
        dst_rel = entry.get("dst")
        if not isinstance(src_rel, str) or not isinstance(dst_rel, str):
            continue
        src = (project_root / src_rel).resolve()
        if not src.exists():
            raise FileNotFoundError(
                f"workspace files: source does not exist: {src}"
            )
        dst = workspace_path / dst_rel
        if dst.is_symlink() or dst.exists():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        count += 1
    return count


def build_claude_settings(
    agents: list[DiscoveredAgent],
    allowed_builtin: list[str] | None = None,
    mcp_prefix: str = CLAUDE_MCP_PREFIX,
) -> dict[str, object]:
    """Build the Claude Code settings document for a workspace.

    ``allowed_builtin`` lists built-in tools (e.g. ``Read``, ``Glob``,
    ``Grep``) that the workspace explicitly re-enables. Anything in
    ``DENIED_BUILTIN_TOOLS`` but NOT in this list ends up in ``deny``.
    """
    allow: list[str] = []
    seen: set[str] = set()

    for agent in agents:
        for tool in agent["mcp_tools"]:
            if tool in seen or not tool.startswith(mcp_prefix):
                continue
            seen.add(tool)

            if _is_read_tool_claude(tool, mcp_prefix):
                allow.append(tool)
            else:
                suffix = tool[len(mcp_prefix) :]
                if suffix.endswith("_*"):
                    p = suffix[: -len("_")]
                    for rp in sorted(READ_PREFIXES):
                        read_key = f"{mcp_prefix}{p}_{rp}"
                        if read_key not in seen:
                            seen.add(read_key)
                            allow.append(read_key)

    allow_builtin = {t for t in (allowed_builtin or []) if isinstance(t, str)}
    deny = sorted(t for t in DENIED_BUILTIN_TOOLS if t not in allow_builtin)
    allow_list = sorted(allow) + sorted(allow_builtin)
    return {
        "permissions": {
            "allow": allow_list,
            "deny": deny,
        }
    }


def _claude_tool_to_opencode(tool: str) -> str:
    if tool in CLAUDE_TO_OPENCODE_TOOLS:
        return CLAUDE_TO_OPENCODE_TOOLS[tool]
    if tool.startswith(CLAUDE_MCP_PREFIX):
        suffix = tool[len(CLAUDE_MCP_PREFIX) :]
        return f"{OPENCODE_MCP_PREFIX}{suffix}"
    return tool


def _is_read_tool_opencode(tool: str) -> bool:
    if not tool.startswith(OPENCODE_MCP_PREFIX):
        return False
    suffix = tool[len(OPENCODE_MCP_PREFIX) :]
    parts = suffix.split("_", 1)
    return len(parts) == 2 and any(parts[1].startswith(rp) for rp in READ_PREFIXES)


def _derive_agent_permissions(oc_tools: list[str]) -> dict[str, Permission]:
    permissions: dict[str, Permission] = {}
    for tool in oc_tools:
        if not tool.startswith(OPENCODE_MCP_PREFIX):
            continue
        if _is_read_tool_opencode(tool):
            permissions.setdefault(tool, "allow")
        else:
            permissions.setdefault(tool, "ask")
            suffix = tool[len(OPENCODE_MCP_PREFIX) :]
            if suffix.endswith("_"):
                prefix = suffix[:-1]
                for rp in sorted(READ_PREFIXES):
                    read_key = f"{OPENCODE_MCP_PREFIX}{prefix}_{rp}"
                    permissions.setdefault(read_key, "allow")
    return permissions


_ALWAYS_ON_MCP_TOOLS = (
    f"{OPENCODE_MCP_PREFIX}skill_list",
    f"{OPENCODE_MCP_PREFIX}skill_get_content",
    f"{OPENCODE_MCP_PREFIX}drafter_list_resources",
    f"{OPENCODE_MCP_PREFIX}drafter_get_resource",
)

_ALWAYS_ON_BUILTIN_TOOLS: dict[str, bool] = {
    "todoread": True,
    "todowrite": True,
}


def build_claude_mcp_config(
    mcp_server_name: str,
    mcp_url: str | None,
    mcp_transport: str,
    mcp_command: list[str],
) -> dict[str, object]:
    """Claude Code ``--mcp-config`` payload.

    When ``mcp_url`` is set, emits a remote (``http``/``sse``) server
    entry. Otherwise falls back to a stdio command entry.
    """
    if mcp_url:
        entry: dict[str, object] = {"type": mcp_transport, "url": mcp_url}
    else:
        entry = {"command": mcp_command[0], "args": list(mcp_command[1:])}
    return {"mcpServers": {mcp_server_name: entry}}


def _opencode_mcp_entry(
    mcp_url: str | None,
    mcp_transport: str,
    mcp_command: list[str],
) -> dict[str, object]:
    if mcp_url:
        return {"type": "remote", "url": mcp_url, "enabled": True}
    return {"type": "local", "command": mcp_command, "enabled": True}


def build_opencode_config(
    agents: list[DiscoveredAgent],
    mcp_server_name: str,
    mcp_command: list[str],
    mcp_url: str | None = None,
    mcp_transport: str = "http",
) -> dict[str, object]:
    _always_on_tools = {
        **_ALWAYS_ON_BUILTIN_TOOLS,
        f"{OPENCODE_MCP_PREFIX}skill_list": True,
        f"{OPENCODE_MCP_PREFIX}skill_get_content": True,
        f"{OPENCODE_MCP_PREFIX}drafter_list_resources": True,
        f"{OPENCODE_MCP_PREFIX}drafter_get_resource": True,
    }

    agent_entries: dict[str, dict] = {
        "project_manager": {
            "tools": _always_on_tools.copy(),
            "permission": {"time-server_*": "allow"},
        },
    }

    for agent in agents:
        oc_tools = [_claude_tool_to_opencode(t) for t in agent["mcp_tools"]]
        tools_dict: dict[str, bool] = {
            **_ALWAYS_ON_BUILTIN_TOOLS,
            **dict.fromkeys(oc_tools, True),
        }
        for tool_name in _ALWAYS_ON_MCP_TOOLS:
            tools_dict.setdefault(tool_name, True)
        permissions = _derive_agent_permissions(oc_tools)

        agent_entries[agent["name"]] = {
            "description": agent["description"],
            "prompt": agent["prompt"],
            "tools": tools_dict,
            "permission": permissions,
        }

    for name in DISABLED_OPENCODE_AGENTS:
        agent_entries[name] = {"disable": True}

    global_perms: dict[str, Permission] = {"*": "ask"}
    for agent in agents:
        oc_tools = [_claude_tool_to_opencode(t) for t in agent["mcp_tools"]]
        for tool, perm in _derive_agent_permissions(oc_tools).items():
            global_perms.setdefault(tool, perm)
    for always_allow in _ALWAYS_ON_MCP_TOOLS:
        global_perms[always_allow] = "allow"

    return {
        "$schema": OPENCODE_SCHEMA,
        "theme": OPENCODE_THEME,
        "tools": {"skill": False},
        "permission": global_perms,
        "agent": agent_entries,
        "mcp": {
            mcp_server_name: _opencode_mcp_entry(mcp_url, mcp_transport, mcp_command),
        },
    }


class ConfigGenerator:
    """Generates runner configuration files for a workspace.

    Parameters
    ----------
    agentbox_toml:
        Path to agentbox.toml (single source of truth).
    manifest_path:
        Path to tool_manifest.json.
    mcp_server_name:
        MCP server name for OpenCode config.
    mcp_command:
        Command array for MCP server in OpenCode config.
    """

    def __init__(
        self,
        agentbox_toml: Path,
        manifest_path: Path,
        *,
        mcp_server_name: str = "mcp",
        mcp_command: list[str] | None = None,
        mcp_url: str | None = None,
        mcp_transport: str = "http",
        verbose: bool = True,
    ) -> None:
        self.discovery = AgentDiscovery(
            agentbox_toml=agentbox_toml,
            manifest_path=manifest_path,
            mcp_server_name=mcp_server_name,
            verbose=verbose,
        )
        self.mcp_server_name = mcp_server_name
        self.mcp_command = mcp_command or ["mcp_serve.sh"]
        self.mcp_url = mcp_url
        self.mcp_transport = mcp_transport
        self.verbose = verbose

    def generate_for_workspace(
        self,
        workspace_path: Path,
        allowed_tools: set[str] | None = None,
        allowed_builtin_tools: list[str] | None = None,
        files: list[dict] | None = None,
        project_root: Path | None = None,
    ) -> dict[str, Path]:
        """Generate all configs into workspace_path/.agentbox/generated/.

        Parameters
        ----------
        workspace_path:
            Path to the workspace directory.
        allowed_tools:
            Optional set of tool names (with ``mcp__`` prefix) to restrict
            each agent to. When provided, only tools in this set are included
            in the generated configs. Both Claude Code and OpenCode configs
            are generated from the same filtered specification.

        Returns
        -------
        Dict mapping config type to generated file path.
        """
        agents = self.discovery.discover_mcp_agents()

        # Filter agent tools against workspace permissions
        if allowed_tools is not None:
            filtered: list[DiscoveredAgent] = []
            for agent in agents:
                filtered_tools = [t for t in agent["mcp_tools"] if t in allowed_tools]
                if filtered_tools:
                    filtered_agent = dict(agent)
                    filtered_agent["mcp_tools"] = filtered_tools
                    filtered.append(filtered_agent)  # type: ignore[arg-type]
            agents = filtered
            if self.verbose:
                total = sum(len(a["mcp_tools"]) for a in agents)
                print(f"  Filtered to {len(agents)} agents with {total} allowed tools")

        generated_dir = workspace_path / ".agentbox" / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)

        # Claude Code agents.json
        claude_agents = build_claude_agents(agents)
        claude_agents_path = generated_dir / "claude_agents.json"
        claude_agents_path.write_text(
            json.dumps(claude_agents, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if self.verbose:
            print(f"  Wrote {len(claude_agents)} agents to {claude_agents_path}")

        # Claude Code settings.json
        claude_settings = build_claude_settings(
            agents, allowed_builtin_tools, self.discovery.claude_mcp_prefix
        )
        claude_settings_path = generated_dir / "claude_settings.json"
        claude_settings_path.write_text(
            json.dumps(claude_settings, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if self.verbose:
            allow_count = len(claude_settings["permissions"]["allow"])  # type: ignore[union-attr]
            print(f"  Wrote {allow_count} permissions to {claude_settings_path}")

        # Mirror to <workspace>/.claude/settings.json so Claude Code's cwd
        # auto-load picks up the same deny/allow when an interactive
        # launcher does not pass --settings explicitly.
        mirror_dir = workspace_path / ".claude"
        mirror_dir.mkdir(parents=True, exist_ok=True)
        mirror_path = mirror_dir / "settings.json"
        existing: dict = {}
        if mirror_path.is_file():
            try:
                existing = json.loads(mirror_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        existing["permissions"] = claude_settings["permissions"]
        existing.setdefault("theme", "dark")
        mirror_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Materialize declarative file copies into the workspace cwd so
        # agents can read reference docs as plain files.
        if files and project_root is not None:
            _materialize_workspace_files(workspace_path, files, project_root)

        # Claude MCP config (remote URL if set, stdio command otherwise).
        claude_mcp_config = build_claude_mcp_config(
            mcp_server_name=self.mcp_server_name,
            mcp_url=self.mcp_url,
            mcp_transport=self.mcp_transport,
            mcp_command=self.mcp_command,
        )
        claude_mcp_config_path = generated_dir / "claude_mcp.json"
        claude_mcp_config_path.write_text(
            json.dumps(claude_mcp_config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if self.verbose:
            kind = "remote" if self.mcp_url else "stdio"
            print(f"  Wrote {kind} Claude MCP config to {claude_mcp_config_path}")

        # OpenCode config
        opencode_config = build_opencode_config(
            agents,
            mcp_server_name=self.mcp_server_name,
            mcp_command=self.mcp_command,
            mcp_url=self.mcp_url,
            mcp_transport=self.mcp_transport,
        )
        opencode_path = generated_dir / "opencode.json"
        opencode_path.write_text(
            json.dumps(opencode_config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if self.verbose:
            agent_names = [
                k
                for k, v in opencode_config["agent"].items()  # type: ignore[union-attr]
                if not v.get("disable")  # type: ignore[union-attr]
            ]
            print(f"  Wrote {len(agent_names)} opencode agents to {opencode_path}")

        return {
            "claude_agents": claude_agents_path,
            "claude_settings": claude_settings_path,
            "claude_mcp": claude_mcp_config_path,
            "opencode": opencode_path,
        }

    def get_generated_paths(self, workspace_path: Path) -> dict[str, Path]:
        """Return expected paths without generating."""
        generated_dir = workspace_path / ".agentbox" / "generated"
        return {
            "claude_agents": generated_dir / "claude_agents.json",
            "claude_settings": generated_dir / "claude_settings.json",
            "claude_mcp": generated_dir / "claude_mcp.json",
            "opencode": generated_dir / "opencode.json",
        }
