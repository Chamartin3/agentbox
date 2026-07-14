"""Agents domain — entity + manager pairs, plus multi-table managers.

One file per table (entity + manager together). The manager is the public
surface; the entity is importable directly for cross-domain FK references.
"""
from __future__ import annotations

from agentbox.core.db.agents.agent import (
	Agent,
	AgentManager,
	ActiveAgentVersion,
	ActiveAgentVersionManager,
	AgentMeta,
	AgentMetaManager,
	AgentRunnerProfile,
	AgentRunnerProfileManager,
)
from agentbox.core.db.agents.agent_def import AgentDefManager
from agentbox.core.db.agents.config_event import (
	AgentConfigEvent,
	AgentConfigEventManager,
)
from agentbox.core.db.agents.grant import (
	AgentToolGrant,
	AgentToolGrantManager,
)
from agentbox.core.db.agents.host_env_grant import (
	AgentHostEnvGrant,
	AgentHostEnvGrantManager,
)
from agentbox.core.db.agents.prompt import (
	PromptVersion,
	PromptVersionManager,
)
from agentbox.core.db.agents.sync import (
	AgentSync,
	AgentSyncManager,
)
from agentbox.core.db.agents.version import (
	AgentVersion,
	AgentVersionManager,
	AgentVersionFile,
	AgentVersionFileManager,
	AgentVersionRating,
	AgentVersionRatingManager,
	AgentVersionComment,
	AgentVersionCommentManager,
)

__all__ = [
	# agent entity + managers
	"Agent",
	"AgentManager",
	"ActiveAgentVersion",
	"ActiveAgentVersionManager",
	"AgentMeta",
	"AgentMetaManager",
	"AgentRunnerProfile",
	"AgentRunnerProfileManager",
	# agent_def manager
	"AgentDefManager",
	# config_event entity + manager
	"AgentConfigEvent",
	"AgentConfigEventManager",
	# grant entity + manager
	"AgentToolGrant",
	"AgentToolGrantManager",
	# host_env_grant entity + manager
	"AgentHostEnvGrant",
	"AgentHostEnvGrantManager",
	# prompt entity + manager
	"PromptVersion",
	"PromptVersionManager",
	# sync entity + manager
	"AgentSync",
	"AgentSyncManager",
	# version entities + managers
	"AgentVersion",
	"AgentVersionManager",
	"AgentVersionFile",
	"AgentVersionFileManager",
	"AgentVersionRating",
	"AgentVersionRatingManager",
	"AgentVersionComment",
	"AgentVersionCommentManager",
]
