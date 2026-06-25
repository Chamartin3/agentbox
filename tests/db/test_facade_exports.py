"""Regression guard for the ``agentbox.core.db`` façade.

The façade is the canonical import path for everything persistence-related.
If a name disappears from ``__all__`` (or stops being importable), call
sites break.
"""

from __future__ import annotations

import agentbox.core.db as data
from agentbox.core.db.store import SessionStore as direct


EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        # SQLModel entities
        "ActiveAgentVersion",
        "ActiveResourceVersion",
        "Agent",
        "AgentConfigEvent",
        "AgentMeta",
        "AgentPromptResourceBinding",
        "AgentRunnerProfile",
        "AgentSync",
        "AgentToolGrant",
        "AgentVersion",
        "AgentVersionComment",
        "AgentVersionFile",
        "AgentVersionRating",
        "ApiToken",
        "Database",
        "get_database",
        "HostEnvCallLog",
        "HostEnvProfile",
        "McpToolDiscoveryCache",
        "PromptVersion",
        "Resource",
        "ResourceBlob",
        "ResourceVersion",
        "Run",
        "RunComment",
        "RunPrompt",
        "Session",
        "Setting",
        "SharedResource",
        "Usage",
        "WebhookDelivery",
        "WorkenvTemplate",
        "Workspace",
        "WorkspaceEnvDoc",
        "WorkspaceEnvDocVersion",
        "WorkspaceFileResourceBinding",
        "WorkspaceHostEnvGrant",
        "WorkspaceMcpOverride",
        "WorkspaceMcpPolicy",
        "WorkspaceMcpToolOverride",
        "WorkspaceRuntimePermission",
        "WorkspaceSubagent",
        # records
        "HostEnvGrant",
        "McpServerSnapshot",
        "McpSnapshot",
        "ResourceSnapshotEntry",
        "RunRecord",
        "RunStatus",
        "RunnerSnapshot",
        "SharedResourceRecord",
        "now_iso",
        "row_to_run",
        # manifest
        "AgentDef",
        "AgentVersionRow",
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
        # schema tables / metadata
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
        "RunSetupStore",
        "SessionStore",
        "SnapshotStore",
        "UsageStore",
        # domain helpers / constants
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
        "RunStore",
        "StartupStore",
        "WorkspaceBuildStore",
        "WorkspaceLookupStore",
        # row types
        "EnvDocRow",
        "PromptVersionRow",
        "RepoResourceRow",
        "ResourceStatus",
        "WorkspaceRow",
        "WorkspaceSource",
    }
)


def test_all_matches_expected() -> None:
    actual = frozenset(data.__all__)
    removed = EXPECTED_EXPORTS - actual
    added = actual - EXPECTED_EXPORTS
    assert not removed, f"facade lost exports: {sorted(removed)}"
    assert not added, (
        f"facade gained exports without updating this test: {sorted(added)}"
    )


def test_every_export_is_importable() -> None:
    missing = [name for name in data.__all__ if not hasattr(data, name)]
    assert not missing, f"declared in __all__ but not present on module: {missing}"


def test_session_store_is_the_store_class() -> None:
    assert data.SessionStore is direct
