"""Config-domain read helpers — self-wiring delegates to the system managers.

Domain callers (agents runtime, engine defaults, workspace builders, MCP
server contexts) use these instead of importing the service layer; the
parsing itself lives on ``SettingManager``. Settings *writes* and
token/crypto policy stay on ``SystemService``.
"""
from __future__ import annotations

import uuid

from agentbox.core.config import load_settings
from agentbox.core.db.database import Database, get_database
from agentbox.core.db.utils import now_iso
from agentbox.core.data.manifests.workspaces import McpServerSpec

__all__ = [
    "load_project_mcp_servers",
    "load_project_shared_assets",
    "load_settings_section",
    "record_host_env_call",
]


def _default_db() -> Database:
    return get_database(str(load_settings().db_path))


def load_settings_section(section: str, *, db: Database | None = None) -> dict:
    """Return all ``{key: value}`` pairs in a section (JSON-deserialised)."""
    return (db or _default_db()).settings.get_settings_section(section)


def load_project_mcp_servers(*, db: Database | None = None) -> list[McpServerSpec]:
    """Project-level MCP servers, validated into ``McpServerSpec``s."""
    return (db or _default_db()).settings.get_project_mcp_servers()


def load_project_shared_assets(*, db: Database | None = None) -> dict[str, str]:
    """Return the project shared-asset roots as ``{name: path}``."""
    return (db or _default_db()).settings.get_project_shared_assets()


def record_host_env_call(
    *,
    run_id: str,
    workspace_id: str,
    capability: str,
    params: dict | None,
    status: str,
    error: str | None = None,
    surface: str = "host_env",
    db: Database | None = None,
) -> str:
    """Insert an audit log row for a host-env call. Returns the row id."""
    row_id = uuid.uuid4().hex
    (db or _default_db()).host_env_call_log.insert_call(
        row_id=row_id,
        run_id=run_id,
        workspace_id=workspace_id,
        capability=capability,
        params=params,
        status=status,
        error=error,
        surface=surface,
        created_at=now_iso(),
    )
    return row_id
