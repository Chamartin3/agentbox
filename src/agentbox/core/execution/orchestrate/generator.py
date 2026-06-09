"""Config generator factory and agent-config helpers extracted from RunSetup."""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.config import Settings
from agentbox.core.engines.render import ConfigGenerator

if TYPE_CHECKING:
    from agentbox.core.workspaces import McpRegistry


def _read_agent_config_json(agent: Any) -> dict[str, Any]:
    """Read the ``config_json`` dict attached to an agent, if any.

    ``config_json`` lives on ``agent_versions`` and is attached to the
    agent object via ``agent.__dict__["_config_json"]`` during DB load.
    Returns the full parsed dict or an empty dict.
    """
    raw = agent.__dict__.get("_config_json") if hasattr(agent, "__dict__") else None
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def make_generator(settings: Settings, store: Any, mcp_registry: McpRegistry | None) -> ConfigGenerator:
    """Build a ConfigGenerator for the current project.

    Reads the MCP manifest from the runtime registry and the tool-manifest
    path from the store to build a complete generator config.
    """
    project_root = settings.project_root
    agentbox_toml = project_root / "agentbox.toml"
    mcp_manifest = _try_get_mcp_manifest(mcp_registry)
    servers = store.get_project_mcp_servers()
    mcp_spec = servers[0] if servers else None
    mcp_server_name = mcp_spec.name if mcp_spec else "mcp"
    mcp_url = mcp_spec.url if mcp_spec else None
    mcp_transport = str(mcp_spec.transport) if mcp_spec else "http"
    mcp_command = (
        mcp_spec.command if mcp_spec and mcp_spec.command else ["mcp_serve.sh"]
    )
    static_manifest_path: Path | None = None
    tool_manifest_path = store.get_tool_manifest_path()
    if tool_manifest_path:
        candidate = project_root / tool_manifest_path
        if candidate.exists():
            static_manifest_path = candidate
    return ConfigGenerator(
        agentbox_toml=agentbox_toml,
        manifest_path=static_manifest_path,
        mcp_manifest=mcp_manifest,
        mcp_server_name=mcp_server_name,
        mcp_url=mcp_url,
        mcp_transport=mcp_transport,
        mcp_command=mcp_command,
        verbose=False,
    )


def _try_get_mcp_manifest(mcp_registry: McpRegistry | None):
    if mcp_registry is None:
        return None
    try:
        return mcp_registry.manifest
    except Exception:
        return None
