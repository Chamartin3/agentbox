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
    AgentManager,
    AgentMetaManager,
    AgentRunnerProfileManager,
    AgentSyncManager,
    AgentToolGrantManager,
    AgentVersionCommentManager,
    AgentVersionFileManager,
    AgentVersionManager,
    AgentVersionRatingManager,
    PromptVersionManager,
)

# Workspaces domain
from agentbox.core.db.managers.workspaces import (
    WorkenvTemplateManager,
    WorkspaceEnvDocManager,
    WorkspaceEnvDocVersionManager,
    WorkspaceHostEnvGrantManager,
    WorkspaceManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceRuntimePermissionManager,
    WorkspaceSubagentManager,
)

# Resources domain
from agentbox.core.db.managers.resources import (
    ActiveResourceVersionManager,
    AgentPromptResourceBindingManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    SharedResourceManager,
    WorkspaceFileResourceBindingManager,
)

# Engines domain
from agentbox.core.db.managers.engines import (
    RunnerProfileManager,
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
    "AgentManager",
    "AgentMetaManager",
    "AgentRunnerProfileManager",
    "AgentSyncManager",
    "AgentToolGrantManager",
    "AgentVersionCommentManager",
    "AgentVersionFileManager",
    "AgentVersionManager",
    "AgentVersionRatingManager",
    "PromptVersionManager",
    # workspaces
    "WorkenvTemplateManager",
    "WorkspaceEnvDocManager",
    "WorkspaceEnvDocVersionManager",
    "WorkspaceHostEnvGrantManager",
    "WorkspaceManager",
    "WorkspaceMcpOverrideManager",
    "WorkspaceMcpPolicyManager",
    "WorkspaceMcpToolOverrideManager",
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
