"""Agents domain managers — catalog index."""
from __future__ import annotations

from agentbox.core.db.managers.agents.agent import (
    AgentManager,
    ActiveAgentVersionManager,
    AgentMetaManager,
    AgentRunnerProfileManager,
)
from agentbox.core.db.managers.agents.version import (
    AgentVersionManager,
    AgentVersionFileManager,
    AgentVersionRatingManager,
    AgentVersionCommentManager,
)
from agentbox.core.db.managers.agents.prompt import PromptVersionManager
from agentbox.core.db.managers.agents.grant import AgentToolGrantManager
from agentbox.core.db.managers.agents.sync import AgentSyncManager
from agentbox.core.db.managers.agents.config_event import AgentConfigEventManager

__all__ = [
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
]
