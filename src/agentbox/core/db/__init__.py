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
# Records & mappers
# ---------------------------------------------------------------------------
from agentbox.core.constants import RunStatus
from agentbox.core.db.execution.records import RunRecord, row_to_run
from agentbox.core.db.execution.snapshots import (
    HostEnvGrant,
    McpServerSnapshot,
    McpSnapshot,
    ResourceSnapshotEntry,
    RunnerSnapshot,
)
from agentbox.core.db.resources.shared._models import SharedResourceRecord
from agentbox.core.db.utils import now_iso

# ---------------------------------------------------------------------------
# Manifest / declarative models (pydantic)
# ---------------------------------------------------------------------------
from agentbox.core.db.agents.manifest import (
    AgentDef,
    AgentManifest,
    AgentSource,
    CompositionConfig,
    SharedRef,
)
from agentbox.core.db.engines.manifest import RunnerManifest, RunnerSpec
from agentbox.core.db.system.manifest import ProjectManifest
from agentbox.core.db.workspaces.manifest import (
    McpServerSpec,
    McpTransport,
    WorkspaceDef,
    WorkspaceFile,
)

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
from agentbox.core.db.resources.crud import ResourcesMixin
from agentbox.core.db.resources.shared import SharedResourcesMixin
from agentbox.core.db.resources.bindings import ResourceBindingsMixin
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
from agentbox.core.db.execution.claude_session import find_session_log, parse_session_log
from agentbox.core.db.resources._rows import hash_blobs as hash_blobs
from agentbox.core.db.engines.models import RunnerProfileStats
from agentbox.core.db.engines.profiles import (
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfilePatch,
)
from agentbox.core.db.engines.seeds import (
    DEFAULT_PROFILES,
    seed_default_runner_profiles,
)
from agentbox.core.db.execution.transcripts import read_transcript

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
from agentbox.core.db.execution.events import (
    DoneEvent,
    LogEvent,
    RetryEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    TimeoutEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
    ValidationEvent,
)

# ---------------------------------------------------------------------------
# Protocols (typed store surfaces)
# ---------------------------------------------------------------------------
from agentbox.core.db.protocols import (
    RunSetupStore,
    RunStore,
    SnapshotStore,
    StartupStore,
    UsageStore,
    WorkspaceBuildStore,
    WorkspaceLookupStore,
)

# ---------------------------------------------------------------------------
# Row types (TypedDict query result shapes)
# ---------------------------------------------------------------------------
from agentbox.core.db.row_types import (
    AgentConfigEventRow,
    AgentMetaRow,
    AgentSyncRow,
    AgentToolGrantRow,
    AgentVersionCommentRow,
    AgentVersionFileRow,
    AgentVersionRatingRow,
    AgentVersionRow,
    EnvDocRow,
    PromptVersionRow,
    RepoResourceRow,
    ResourceStatus,
    VersionFileUploadRow,
    WorkspaceRow,
    WorkspaceSource,
    _AgentMetaPatchFields,
    _AgentSyncPatchFields,
    _AgentToolGrantPatchFields,
    _AgentVersionFields,
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
    # records
    "RunStatus",
    "HostEnvGrant",
    "McpServerSnapshot",
    "McpSnapshot",
    "ResourceSnapshotEntry",
    "RunnerSnapshot",
    "RunRecord",
    "SharedResourceRecord",
    "now_iso",
    "row_to_run",
    # manifest
    "AgentDef",
    "AgentManifest",
    "AgentSource",
    "CompositionConfig",
    "McpServerSpec",
    "McpTransport",
    "ProjectManifest",
    "RunnerManifest",
    "RunnerSpec",
    "SharedRef",
    "WorkspaceDef",
    "WorkspaceFile",
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
    "ResourceBindingsMixin",
    "ResourcesMixin",
    "RuntimePermissionsMixin",
    "SharedResourcesMixin",
    "WorkenvTemplatesMixin",
    "WorkspacesMixin",
    # store
    "SessionStore",
    # domain helpers
    "DEFAULT_PROFILES",
    "RunnerProfile",
    "RunnerProfileCreate",
    "RunnerProfilePatch",
    "RunnerProfileStats",
    "find_session_log",
    "parse_session_log",
    "read_transcript",
    "seed_default_runner_profiles",
    "hash_blobs",
    # events
    "DoneEvent",
    "LogEvent",
    "RetryEvent",
    "RunEvent",
    "TextEvent",
    "ThinkingEvent",
    "TimeoutEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "UsageEvent",
    "ValidationEvent",
    # protocols
    "RunSetupStore",
    "RunStore",
    "SnapshotStore",
    "StartupStore",
    "UsageStore",
    "WorkspaceBuildStore",
    "WorkspaceLookupStore",
    # row types
    "AgentConfigEventRow",
    "AgentMetaRow",
    "AgentSyncRow",
    "AgentToolGrantRow",
    "AgentVersionCommentRow",
    "AgentVersionFileRow",
    "AgentVersionRatingRow",
    "AgentVersionRow",
    "EnvDocRow",
    "PromptVersionRow",
    "RepoResourceRow",
    "ResourceStatus",
    "VersionFileUploadRow",
    "WorkspaceRow",
    "WorkspaceSource",
    "_AgentMetaPatchFields",
    "_AgentSyncPatchFields",
    "_AgentToolGrantPatchFields",
    "_AgentVersionFields",
]
