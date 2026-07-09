"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Tables are grouped by domain in submodules; everything is re-exported here.
"""

from __future__ import annotations

from agentbox.core.db._metadata import metadata

from agentbox.core.db.schema.agents import (
    active_agent_versions,
    agent_config_events,
    agent_meta,
    agent_runner_profiles,
    agent_sync,
    agent_tool_grants,
    agent_host_env_grants,
    agent_version_comments,
    agent_version_files,
    agent_version_ratings,
    agent_versions,
    agents,
    prompt_versions,
)

from agentbox.core.db.schema.resources import (
    active_resource_versions,
    agent_prompt_resource_bindings,
    resource_blobs,
    resource_versions,
    resources,
    shared_resources,
    workspace_file_resource_bindings,
)

from agentbox.core.db.schema.engines import (
    runner_profiles,
)

from agentbox.core.db.schema.execution import (
    run_comments,
    run_prompts,
    runs,
    sessions,
    usage,
    webhook_deliveries,
)

from agentbox.core.db.schema.system import (
    api_tokens,
    host_env_call_log,
    host_env_profiles,
    mcp_tool_discovery_cache,
    settings,
)

from agentbox.core.db.schema.workspaces import (
    workspace_env_doc_versions,
    workspace_env_docs,
    workspace_mcp_overrides,
    workspace_mcp_policies,
    workspace_mcp_tool_overrides,
    workspace_runtime_permissions,
    workspace_subagents,
    workspaces,
)

__all__ = [
    "metadata",
    # agents
    "active_agent_versions",
    "agent_config_events",
    "agent_meta",
    "agent_runner_profiles",
    "agent_sync",
    "agent_tool_grants",
    "agent_host_env_grants",
    "agent_version_comments",
    "agent_version_files",
    "agent_version_ratings",
    "agent_versions",
    "agents",
    "prompt_versions",
    # resources
    "active_resource_versions",
    "agent_prompt_resource_bindings",
    "resource_blobs",
    "resource_versions",
    "resources",
    "shared_resources",
    "workspace_file_resource_bindings",
    # engines
    "runner_profiles",
    # execution
    "run_comments",
    "run_prompts",
    "runs",
    "sessions",
    "usage",
    "webhook_deliveries",
    # system
    "api_tokens",
    "host_env_call_log",
    "host_env_profiles",
    "mcp_tool_discovery_cache",
    "settings",
    # workspaces
    "workspace_env_doc_versions",
    "workspace_env_docs",
    "workspace_mcp_overrides",
    "workspace_mcp_policies",
    "workspace_mcp_tool_overrides",
    "workspace_runtime_permissions",
    "workspace_subagents",
    "workspaces",
]
