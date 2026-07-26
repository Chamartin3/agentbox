"""Core.db facade — managers only.

The public interface of ``agentbox.core.db`` is exclusively the Manager
classes.  Import managers from here:

    from agentbox.core.db import RunManager, AgentManager, WorkspaceManager

``Database`` and ``get_database`` are internal composition wiring that owns the
engine lifecycle.  They are importable only from ``agentbox.core.db.database``
by a named allowlist (service/base.py, the three deps.py, cli/ops/migrate.py,
the two mcp/servers/*/context.py).  Everything else uses managers.

Shared data shapes (rows, snapshots) live in
``core.data`` / ``core.protocols`` / ``core.events``.  SQLModel entities live in
their per-domain packages (``core.db.runs``, ``core.db.agents``, …) alongside
their managers, one file per table (entity + manager together).  The entities'
shared ``MetaData`` (``core.db.base.metadata``) is the single schema source of
truth.  Entities are not re-exported by this façade.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Managers (the only public surface of core.db)
# ---------------------------------------------------------------------------
from agentbox.core.db.runs import (
    RunCommentManager,
    RunManager,
    RunPromptManager,
    SessionManager,
    UsageManager,
    WebhookDeliveryManager,
)
from agentbox.core.db.agents import (
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
)
from agentbox.core.db.workspaces import (
    # workspaces
    WorkspaceEnvDocManager,
    WorkspaceEnvDocVersionManager,
    WorkspaceEnvVarManager,
    WorkspaceManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceCredentialManager,
    WorkspaceReadManager,
    WorkspaceRuntimePermissionManager,
    WorkspaceSubagentManager,
)
from agentbox.core.db.engines import RunnerProfileManager
from agentbox.core.db.resources import (
    ActiveResourceVersionManager,
    AgentPromptResourceBindingManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    WorkspaceFileResourceBindingManager,
)
from agentbox.core.db.system import (
    HostEnvCallLogManager,
    HostEnvProfileManager,
    ManagedCredentialManager,
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
    "WorkspaceEnvVarManager",
    "WorkspaceManager",
    "WorkspaceMcpOverrideManager",
    "WorkspaceMcpPolicyManager",
    "WorkspaceMcpToolOverrideManager",
    "WorkspaceCredentialManager",
    "WorkspaceReadManager",
    "WorkspaceRuntimePermissionManager",
    "WorkspaceSubagentManager",
    # resources
    "ActiveResourceVersionManager",
    "AgentPromptResourceBindingManager",
    "ResourceBlobManager",
    "ResourceManager",
    "ResourceVersionManager",
    "WorkspaceFileResourceBindingManager",
    # engines
    "RunnerProfileManager",
    # system
    "HostEnvCallLogManager",
    "HostEnvProfileManager",
    "ManagedCredentialManager",
    "McpToolDiscoveryCacheManager",
    "SettingManager",
]
