"""Persistent data + declarative models for agentbox.

This package is the single home for persistent data shapes: SQLAlchemy
schema, CRUD store, analytics queries, prompt/agent version history,
transcript reader, and parsed-TOML manifest models.

**Import from this package, not its submodules.** The façade below
re-exports every public symbol — mixins, tables, records, manifest
models, helpers — so call sites never need to reach into
``agentbox.core.data.<sub>`` directly. This keeps the package boundary
auditable and lets us reorganize submodules without breaking callers.

See ``docs/plans/24-core-data-consolidation.md`` for the in-progress
reorganization.
"""

# ---------------------------------------------------------------------------
# Records & mappers
# ---------------------------------------------------------------------------
# RunStatus lives in core.constants but is re-exported here so callers can
# get every persistent-data symbol from one façade (per data/__init__.py rule).
from agentbox.core.constants import RunStatus
from agentbox.core.data.records import (
    HostEnvGrant,
    McpServerSnapshot,
    McpSnapshot,
    ResourceSnapshotEntry,
    RunnerSnapshot,
    RunRecord,
    SharedResourceRecord,
    now_iso,
    row_to_run,
)

# ---------------------------------------------------------------------------
# Manifest / declarative models (pydantic)
# ---------------------------------------------------------------------------
from agentbox.core.data.manifest import (
    AgentDef,
    AgentManifest,
    AgentSource,
    CompositionConfig,
    McpServerSpec,
    McpTransport,
    ProjectManifest,
    RunnerManifest,
    RunnerSpec,
    SharedRef,
    WorkspaceDef,
    WorkspaceFile,
)

# ---------------------------------------------------------------------------
# Schema (SQLAlchemy Core tables + shared metadata)
# ---------------------------------------------------------------------------
from agentbox.core.data.schema import (
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
from agentbox.core.data.agent_config_events import AgentConfigEventsMixin
from agentbox.core.data.agent_sync import AgentSyncMixin
from agentbox.core.data.agent_tool_grants import AgentToolGrantsMixin
from agentbox.core.data.agent_versions import AgentVersionsMixin
from agentbox.core.data.analytics import AnalyticsMixin
from agentbox.core.data.api_tokens import ApiTokensMixin
from agentbox.core.data.env_docs import EnvDocsMixin
from agentbox.core.data.host_env import HostEnvMixin
from agentbox.core.data.mcp_discovery import McpDiscoveryMixin
from agentbox.core.data.mcp_overrides import McpOverridesMixin
from agentbox.core.data.project_config import ProjectConfigMixin
from agentbox.core.data.prompts import PromptVersionsMixin
from agentbox.core.data.resource_bindings import ResourceBindingsMixin
from agentbox.core.data.resources import ResourcesMixin
from agentbox.core.data.runner_profiles import RunnerProfilesMixin
from agentbox.core.data.runtime_permissions import RuntimePermissionsMixin
from agentbox.core.data.settings import SettingsMixin
from agentbox.core.data.shared_resources import SharedResourcesMixin
from agentbox.core.data.workspaces import WorkspacesMixin

# ---------------------------------------------------------------------------
# Store façade
# ---------------------------------------------------------------------------
from agentbox.core.data.store import SessionStore

# ---------------------------------------------------------------------------
# Domain-specific helpers / constants
# ---------------------------------------------------------------------------
from agentbox.core.data.analytics import _duration_ms_expr  # noqa: F401
from agentbox.core.data.claude_session import find_session_log, parse_session_log
from agentbox.core.data.mcp_overrides import VALID_POLICIES
from agentbox.core.data.resources import _hash_blobs  # noqa: F401
from agentbox.core.data.runner_profiles import (
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfilePatch,
    RunnerProfileStats,
)
from agentbox.core.data.runner_profiles_seed import (
    DEFAULT_PROFILES,
    seed_default_runner_profiles,
)
from agentbox.core.data.transcripts import read_transcript

# Re-bind schema table names that collide with submodule names. The mixin
# imports above register submodules as attributes of this package, which
# shadows the Table objects imported from ``schema``. Re-import last so the
# facade exports the Tables, not the submodules.
from agentbox.core.data.schema import (  # noqa: E402,F811
    agent_config_events,
    agent_sync,
    agent_tool_grants,
    agent_versions,
    api_tokens,
    prompt_versions,
    resources,
    runner_profiles,
    settings,
    workspaces,
)

__all__ = [
    "RunStatus",
    # records
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
    # schema
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
    # mixins
    "AgentConfigEventsMixin",
    "AgentSyncMixin",
    "AgentToolGrantsMixin",
    "AgentVersionsMixin",
    "AnalyticsMixin",
    "ApiTokensMixin",
    "EnvDocsMixin",
    "HostEnvMixin",
    "McpDiscoveryMixin",
    "McpOverridesMixin",
    "ProjectConfigMixin",
    "PromptVersionsMixin",
    "ResourceBindingsMixin",
    "ResourcesMixin",
    "RunnerProfilesMixin",
    "RuntimePermissionsMixin",
    "SettingsMixin",
    "SharedResourcesMixin",
    "WorkspacesMixin",
    # store
    "SessionStore",
    # domain helpers
    "DEFAULT_PROFILES",
    "RunnerProfile",
    "RunnerProfileCreate",
    "RunnerProfilePatch",
    "RunnerProfileStats",
    "VALID_POLICIES",
    "find_session_log",
    "parse_session_log",
    "read_transcript",
    "seed_default_runner_profiles",
]
