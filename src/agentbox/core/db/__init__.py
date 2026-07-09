"""Core.db facade — managers only.

The public interface of ``agentbox.core.db`` is exclusively the Manager
classes (plan 109).  Import managers from here:

    from agentbox.core.db import RunManager, AgentManager, WorkspaceManager

``Database`` and ``get_database`` are internal composition wiring that owns the
engine lifecycle.  They are importable only from ``agentbox.core.db.database``
by a named allowlist (service/base.py, the three deps.py, cli/ops/migrate.py,
the two mcp/servers/*/context.py).  Everything else uses managers.

Shared data shapes (``SharedResourceRecord``, rows, snapshots) live in
``core.data`` / ``core.protocols`` / ``core.events``.  Schema tables and SQLModel
entities are in ``core.db.schema`` / ``core.db.models`` — not re-exported here.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Managers (the only public surface of core.db)
# ---------------------------------------------------------------------------
from agentbox.core.db.managers import (
    # runs
    RunCommentManager,
    RunManager,
    RunPromptManager,
    SessionManager,
    UsageManager,
    WebhookDeliveryManager,
    # agents
    ActiveAgentVersionManager,
    AgentConfigEventManager,
    AgentDefManager,
    AgentManager,
    AgentMetaManager,
    AgentRunnerProfileManager,
    AgentSyncManager,
    AgentToolGrantManager,
    AgentHostEnvGrantManager,
    AgentVersionCommentManager,
    AgentVersionFileManager,
    AgentVersionManager,
    AgentVersionRatingManager,
    PromptVersionManager,
    # workspaces
    WorkspaceEnvDocManager,
    WorkspaceEnvDocVersionManager,
    WorkspaceManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceReadManager,
    WorkspaceRuntimePermissionManager,
    WorkspaceSubagentManager,
    # resources
    ActiveResourceVersionManager,
    AgentPromptResourceBindingManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    SharedResourceManager,
    WorkspaceFileResourceBindingManager,
    # engines
    RunnerProfileManager,
    # system
    ApiTokenManager,
    HostEnvCallLogManager,
    HostEnvProfileManager,
    McpToolDiscoveryCacheManager,
    SettingManager,
)

__all__ = [
    # runs
    "RunCommentManager",
    "RunManager",
    "RunPromptManager",
    "SessionManager",
    "UsageManager",
    "WebhookDeliveryManager",
    # agents
    "ActiveAgentVersionManager",
    "AgentConfigEventManager",
    "AgentDefManager",
    "AgentManager",
    "AgentMetaManager",
    "AgentRunnerProfileManager",
    "AgentSyncManager",
    "AgentToolGrantManager",
    "AgentHostEnvGrantManager",
    "AgentVersionCommentManager",
    "AgentVersionFileManager",
    "AgentVersionManager",
    "AgentVersionRatingManager",
    "PromptVersionManager",
    # workspaces
    "WorkspaceEnvDocManager",
    "WorkspaceEnvDocVersionManager",
    "WorkspaceManager",
    "WorkspaceMcpOverrideManager",
    "WorkspaceMcpPolicyManager",
    "WorkspaceMcpToolOverrideManager",
    "WorkspaceReadManager",
    "WorkspaceRuntimePermissionManager",
    "WorkspaceSubagentManager",
    # resources
    "ActiveResourceVersionManager",
    "AgentPromptResourceBindingManager",
    "ResourceBlobManager",
    "ResourceManager",
    "ResourceVersionManager",
    "SharedResourceManager",
    "WorkspaceFileResourceBindingManager",
    # engines
    "RunnerProfileManager",
    # system
    "ApiTokenManager",
    "HostEnvCallLogManager",
    "HostEnvProfileManager",
    "McpToolDiscoveryCacheManager",
    "SettingManager",
]
