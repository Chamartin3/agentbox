"""Managers catalog — re-exports every Manager.

Callers import managers from here or from the ``core.db`` façade:
    from agentbox.core.db.managers.runs import RunManager
    from agentbox.core.db.managers import RunManager, WorkspaceManager
"""
from __future__ import annotations

# Runs domain
from agentbox.core.db.managers.runs import (
    RunCommentManager,
    RunManager,
    RunPromptManager,
    SessionManager,
    UsageManager,
    WebhookDeliveryManager,
)

# Agents domain
from agentbox.core.db.managers.agents import (
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
)

# Workspaces domain
from agentbox.core.db.managers.workspaces import (
    WorkspaceEnvDocManager,
    WorkspaceEnvDocVersionManager,
    WorkspaceManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceReadManager,
    WorkspaceRuntimePermissionManager,
    WorkspaceSubagentManager,
)


# System domain
from agentbox.core.db.managers.system import (
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
    # system
    "ApiTokenManager",
    "HostEnvCallLogManager",
    "HostEnvProfileManager",
    "McpToolDiscoveryCacheManager",
    "SettingManager",
]
