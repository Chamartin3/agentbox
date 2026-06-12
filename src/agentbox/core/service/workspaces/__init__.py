"""Service layer for workspace orchestration.

Wraps the registry CRUD, on-disk file ops, permission overlay,
MCP-derived tool resolution, config generation, and skill discovery
that used to live in ``api/routes/workspaces.py``. Routes become a
thin transport adapter: parse -> call -> map domain errors to HTTP.

Dependency injection is explicit (``store``, ``settings``, ``loader``,
``mcp_manifest``) so this package has no import of FastAPI deps. That
lets MCP tools and the CLI consume the same use-cases.

This module is the stable public facade; concrete implementations live
in the ``registry`` / ``permissions`` / ``mcp`` / ``configs`` /
``skills`` / ``files`` / ``errors`` submodules.

Domain errors raised here:

* :class:`WorkspaceNotFound` -- unknown registry name.
* :class:`WorkspaceExists` -- create called for a name that's already
  registered (registry uniqueness violation).
* :class:`WorkspacePathEscape` -- file ops where the resolved path
  walks above the workspace root.
* :class:`AgentNotFound` -- re-exported from
  :mod:`core.service.prompts` for the legacy agent-centric endpoints.
"""

from __future__ import annotations

from agentbox.core.service.prompts import AgentNotFound

from .configs import (
    generate_configs_by_name,
    generate_configs_for_agent,
    generate_legacy_runner_configs,
)
from .errors import WorkspaceExists, WorkspaceNotFound, WorkspacePathEscape
from .files import (
    create_workspace_for_agent,
    get_workspace_for_agent,
    is_user_file,
    read_file_by_name,
    read_file_for_agent,
    reset_workspace_for_agent,
    resolve_workspace_path,
    write_file_by_name,
    write_file_for_agent,
)
from .mcp import refresh_workspace_mcp_discovery, resolve_workspace_mcp
from .permissions import (
    get_permissions,
    get_workspace_mcp_tools,
    load_effective_permissions,
    set_permissions,
)
from .registry import (
    create_workspace_registry,
    delete_workspace_registry,
    get_workspace_by_name,
    list_workspaces_enriched,
)
from .skills import (
    generate_skills_by_name,
    get_skill_content_by_name,
    list_skills_by_name,
    list_skills_for_agent,
)

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
    "generate_legacy_runner_configs",
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
    # MCP overlay (not in original __all__ but used by other modules)
    "resolve_workspace_mcp",
    "refresh_workspace_mcp_discovery",
    "load_effective_permissions",
]
