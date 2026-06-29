"""Core.db package — single persistence + data-shapes package.

This is the consolidated home for all persistent data shapes: SQLModel
entities, Database access point, SQLAlchemy schema tables, the
SessionStore (legacy persistence), domain types, events, protocols,
and manifest models.

**Import from this package, not its submodules.**
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# SQLModel entity classes (the ORM layer)
# ---------------------------------------------------------------------------
from agentbox.core.db.models import (
    # runs
    Run,
    RunComment,
    RunPrompt,
    Session,
    Usage,
    WebhookDelivery,
    # agents
    ActiveAgentVersion,
    Agent,
    AgentConfigEvent,
    AgentMeta,
    AgentRunnerProfile,
    AgentSync,
    AgentToolGrant,
    AgentVersion,
    AgentVersionComment,
    AgentVersionFile,
    AgentVersionRating,
    PromptVersion,
    # workspaces
    WorkenvTemplate,
    Workspace,
    WorkspaceEnvDoc,
    WorkspaceEnvDocVersion,
    WorkspaceHostEnvGrant,
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
    WorkspaceRuntimePermission,
    WorkspaceSubagent,
    # resources
    ActiveResourceVersion,
    AgentPromptResourceBinding,
    Resource,
    ResourceBlob,
    ResourceVersion,
    SharedResource,
    WorkspaceFileResourceBinding,
    # engines — NOTE: RunnerProfile (SQLModel) is NOT re-exported here;
    # the Pydantic RunnerProfile from engines/profiles.py takes precedence.
    # system
    ApiToken,
    HostEnvCallLog,
    HostEnvProfile,
    McpToolDiscoveryCache,
    Setting,
)

# ---------------------------------------------------------------------------
# Database access point
# ---------------------------------------------------------------------------
from agentbox.core.db.database import Database, get_database

# ---------------------------------------------------------------------------
# Constants & persistence models
# ---------------------------------------------------------------------------
from agentbox.core.constants import RunStatus
from agentbox.core.db.resources.shared._models import SharedResourceRecord

# ---------------------------------------------------------------------------
# Schema (SQLAlchemy Core tables + shared metadata)
# ---------------------------------------------------------------------------
from agentbox.core.db.schema import (
    active_agent_versions,
    active_resource_versions,
    agent_config_events,
    agent_meta,
    agent_prompt_resource_bindings,
    agent_runner_profiles,
    agent_sync,
    agent_tool_grants,
    agent_version_comments,
    agent_version_files,
    agent_version_ratings,
    agent_versions,
    agents,
    api_tokens,
    host_env_call_log,
    host_env_profiles,
    mcp_tool_discovery_cache,
    metadata,
    prompt_versions,
    resource_blobs,
    resource_versions,
    resources,
    run_comments,
    run_prompts,
    runner_profiles,
    runs,
    sessions,
    settings,
    shared_resources,
    usage,
    webhook_deliveries,
    workspace_env_doc_versions,
    workspace_env_docs,
    workspace_file_resource_bindings,
    workspace_host_env_grants,
    workspace_mcp_overrides,
    workspace_mcp_policies,
    workspace_mcp_tool_overrides,
    workspace_runtime_permissions,
    workspace_subagents,
    workspaces,
)

# ---------------------------------------------------------------------------
# Mixins (composed into SessionStore — exposed for type hints & tests)
# ---------------------------------------------------------------------------
from agentbox.core.db.agents.events import AgentConfigEventsMixin
from agentbox.core.db.agents.sync import AgentSyncMixin
from agentbox.core.db.agents.grants import AgentToolGrantsMixin
from agentbox.core.db.agents.versions import AgentVersionsMixin
from agentbox.core.db.agents.prompts import PromptVersionsMixin
from agentbox.core.db.workspaces.crud import WorkspacesMixin
from agentbox.core.db.workspaces.env_docs import EnvDocsMixin
from agentbox.core.db.workspaces.host_env import HostEnvMixin
from agentbox.core.db.workspaces.mcp_discovery import McpDiscoveryMixin
from agentbox.core.db.workspaces.mcp_overrides import McpOverridesMixin
from agentbox.core.db.workspaces.runtime_permissions import RuntimePermissionsMixin
from agentbox.core.db.workspaces.templates import WorkenvTemplatesMixin

# ---------------------------------------------------------------------------
# Store façade (legacy persistence)
# ---------------------------------------------------------------------------
from agentbox.core.db.store import SessionStore

# ---------------------------------------------------------------------------
# Domain-specific helpers / constants
# ---------------------------------------------------------------------------
from agentbox.core.db.engines.seeds import (
    DEFAULT_PROFILES,
    seed_default_runner_profiles,
)

# Re-bind schema table names that collide with submodule names.
from agentbox.core.db.schema import (  # noqa: E402,F811
    agent_config_events,
    agent_sync,
    agent_tool_grants,
    agent_versions,
    agents,
    api_tokens,
    prompt_versions,
    resources,
    runner_profiles,
    runs,
    settings,
    workenv_templates,
    workspaces,
)

__all__ = [
    # SQLModel entities
    "Run",
    "RunComment",
    "RunPrompt",
    "Session",
    "Usage",
    "WebhookDelivery",
    "ActiveAgentVersion",
    "Agent",
    "AgentConfigEvent",
    "AgentMeta",
    "AgentRunnerProfile",
    "AgentSync",
    "AgentToolGrant",
    "AgentVersion",
    "AgentVersionComment",
    "AgentVersionFile",
    "AgentVersionRating",
    "PromptVersion",
    "WorkenvTemplate",
    "Workspace",
    "WorkspaceEnvDoc",
    "WorkspaceEnvDocVersion",
    "WorkspaceHostEnvGrant",
    "WorkspaceMcpOverride",
    "WorkspaceMcpPolicy",
    "WorkspaceMcpToolOverride",
    "WorkspaceRuntimePermission",
    "WorkspaceSubagent",
    "ActiveResourceVersion",
    "AgentPromptResourceBinding",
    "Resource",
    "ResourceBlob",
    "ResourceVersion",
    "SharedResource",
    "WorkspaceFileResourceBinding",
    "ApiToken",
    "HostEnvCallLog",
    "HostEnvProfile",
    "McpToolDiscoveryCache",
    "Setting",
    # Database
    "Database",
    "get_database",
    # constants + persistence models
    "RunStatus",
    "SharedResourceRecord",
    # schema tables
    "active_agent_versions",
    "active_resource_versions",
    "agent_config_events",
    "agent_meta",
    "agent_prompt_resource_bindings",
    "agent_runner_profiles",
    "agent_sync",
    "agent_tool_grants",
    "agent_version_comments",
    "agent_version_files",
    "agent_version_ratings",
    "agent_versions",
    "agents",
    "api_tokens",
    "host_env_call_log",
    "host_env_profiles",
    "mcp_tool_discovery_cache",
    "metadata",
    "prompt_versions",
    "resource_blobs",
    "resource_versions",
    "resources",
    "run_comments",
    "run_prompts",
    "runner_profiles",
    "runs",
    "sessions",
    "settings",
    "shared_resources",
    "usage",
    "webhook_deliveries",
    "workspace_env_doc_versions",
    "workspace_env_docs",
    "workspace_file_resource_bindings",
    "workspace_host_env_grants",
    "workspace_mcp_overrides",
    "workspace_mcp_policies",
    "workspace_mcp_tool_overrides",
    "workspace_runtime_permissions",
    "workspace_subagents",
    "workspaces",
    "workenv_templates",
    # mixins
    "AgentConfigEventsMixin",
    "AgentSyncMixin",
    "AgentToolGrantsMixin",
    "AgentVersionsMixin",
    "EnvDocsMixin",
    "HostEnvMixin",
    "McpDiscoveryMixin",
    "McpOverridesMixin",
    "PromptVersionsMixin",
    "RuntimePermissionsMixin",
    "WorkenvTemplatesMixin",
    "WorkspacesMixin",
    # store
    "SessionStore",
    # domain helpers
    "DEFAULT_PROFILES",
    "seed_default_runner_profiles",
]
