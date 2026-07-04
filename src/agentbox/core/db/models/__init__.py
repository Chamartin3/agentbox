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
    WorkspaceHostEnvGrant,
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
    WorkspaceRuntimePermission,
    WorkspaceSubagent,
)

# Resources domain
from agentbox.core.db.models.resources import (
    ActiveResourceVersion,
    AgentPromptResourceBinding,
    Resource,
    ResourceBlob,
    ResourceVersion,
    SharedResource,
    WorkspaceFileResourceBinding,
)

# Engines domain
from agentbox.core.db.models.engines import (
    RunnerProfile,
)

# System domain
from agentbox.core.db.models.system import (
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
    "AgentVersion",
    "AgentVersionComment",
    "AgentVersionFile",
    "AgentVersionRating",
    "PromptVersion",
    # workspaces
    "Workspace",
    "WorkspaceEnvDoc",
    "WorkspaceEnvDocVersion",
    "WorkspaceHostEnvGrant",
    "WorkspaceMcpOverride",
    "WorkspaceMcpPolicy",
    "WorkspaceMcpToolOverride",
    "WorkspaceRuntimePermission",
    "WorkspaceSubagent",
    # resources
    "ActiveResourceVersion",
    "AgentPromptResourceBinding",
    "Resource",
    "ResourceBlob",
    "ResourceVersion",
    "SharedResource",
    "WorkspaceFileResourceBinding",
    # engines
    "RunnerProfile",
    # system
    "ApiToken",
    "HostEnvCallLog",
    "HostEnvProfile",
    "McpToolDiscoveryCache",
    "Setting",
]
