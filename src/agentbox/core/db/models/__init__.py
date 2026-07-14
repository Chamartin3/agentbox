"""Models catalog — re-exports every Model.

Callers import models from here or from the ``core.db`` façade:
    from agentbox.core.db.models import Run, Session
    from agentbox.core.db.models.runs import Run
"""
from __future__ import annotations

# Runs domain
from agentbox.core.db.models.runs import (
    Run,
    RunComment,
    RunPrompt,
    Session,
    Usage,
    WebhookDelivery,
)

# Agents domain
from agentbox.core.db.models.agents import (
    ActiveAgentVersion,
    Agent,
    AgentConfigEvent,
    AgentMeta,
    AgentRunnerProfile,
    AgentSync,
    AgentToolGrant,
    AgentHostEnvGrant,
    AgentVersion,
    AgentVersionComment,
    AgentVersionFile,
    AgentVersionRating,
    PromptVersion,
)

# Workspaces domain
from agentbox.core.db.models.workspaces import (
    Workspace,
    WorkspaceEnvDoc,
    WorkspaceEnvDocVersion,
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
    WorkspaceRuntimePermission,
    WorkspaceSubagent,
)

# System domain
from agentbox.core.db.system import (
    ApiToken,
    HostEnvCallLog,
    HostEnvProfile,
    McpToolDiscoveryCache,
    Setting,
)

__all__ = [
    # runs
    "Run",
    "RunComment",
    "RunPrompt",
    "Session",
    "Usage",
    "WebhookDelivery",
    # agents
    "ActiveAgentVersion",
    "Agent",
    "AgentConfigEvent",
    "AgentMeta",
    "AgentRunnerProfile",
    "AgentSync",
    "AgentToolGrant",
    "AgentHostEnvGrant",
    "AgentVersion",
    "AgentVersionComment",
    "AgentVersionFile",
    "AgentVersionRating",
    "PromptVersion",
    # workspaces
    "Workspace",
    "WorkspaceEnvDoc",
    "WorkspaceEnvDocVersion",
    "WorkspaceMcpOverride",
    "WorkspaceMcpPolicy",
    "WorkspaceMcpToolOverride",
    "WorkspaceRuntimePermission",
    "WorkspaceSubagent",
    # system
    "ApiToken",
    "HostEnvCallLog",
    "HostEnvProfile",
    "McpToolDiscoveryCache",
    "Setting",
]
