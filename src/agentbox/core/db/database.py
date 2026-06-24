"""Database — the single application-level access point for persistence.

``Database`` owns the engine lifecycle, starts up Alembic migrations,
reaps orphaned runs, and exposes every entity manager as a named attribute.

Usage::

    db = Database(Path("/data/agentbox.sqlite"))
    run = db.runs.get("some-run-id")
    db.runs.finish(run_id, status="ok", output="...")
    agents = db.agents.find(team="ml")
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from agentbox.core.db.base.engine import init_engine
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
from agentbox.core.db.managers.engines import RunnerProfileManager
from agentbox.core.db.managers.resources import (
    ActiveResourceVersionManager,
    AgentPromptResourceBindingManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    SharedResourceManager,
    WorkspaceFileResourceBindingManager,
)
from agentbox.core.db.managers.runs import (
    RunCommentManager,
    RunManager,
    RunPromptManager,
    SessionManager,
    UsageManager,
    WebhookDeliveryManager,
)
from agentbox.core.db.managers.system import (
    ApiTokenManager,
    HostEnvCallLogManager,
    HostEnvProfileManager,
    McpToolDiscoveryCacheManager,
    SettingManager,
)
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


class Database:
    """Application-level access point for all persistence operations.

    Each attribute is a ``Manager`` instance bound to the shared engine.

    Attributes matching the plural snake_case of each entity::

        db.runs, db.sessions, db.usage, db.run_comments, db.webhook_deliveries, db.run_prompts
        db.agents, db.agent_versions, db.agent_version_files, db.agent_version_ratings,
            db.agent_version_comments, db.active_agent_versions, db.agent_meta,
            db.agent_runner_profiles, db.prompt_versions, db.agent_tool_grants,
            db.agent_sync, db.agent_config_events
        db.workspaces, db.workspace_env_docs, db.workspace_env_doc_versions,
            db.workspace_mcp_overrides, db.workspace_mcp_tool_overrides,
            db.workspace_mcp_policies, db.workspace_host_env_grants,
            db.workspace_runtime_permissions, db.workspace_subagents,
            db.workenv_templates
        db.resources, db.resource_versions, db.resource_blobs,
            db.active_resource_versions, db.shared_resources,
            db.agent_prompt_resource_bindings, db.workspace_file_resource_bindings
        db.runner_profiles
        db.api_tokens, db.settings, db.host_env_profiles, db.host_env_call_log,
            db.mcp_tool_discovery_cache
    """

    def __init__(self, db_path: Path) -> None:
        self._engine = init_engine(db_path)

        # Runs domain
        self.runs = RunManager(self._engine)
        self.sessions = SessionManager(self._engine)
        self.usage = UsageManager(self._engine)
        self.run_comments = RunCommentManager(self._engine)
        self.webhook_deliveries = WebhookDeliveryManager(self._engine)
        self.run_prompts = RunPromptManager(self._engine)

        # Agents domain
        self.agents = AgentManager(self._engine)
        self.agent_versions = AgentVersionManager(self._engine)
        self.agent_version_files = AgentVersionFileManager(self._engine)
        self.agent_version_ratings = AgentVersionRatingManager(self._engine)
        self.agent_version_comments = AgentVersionCommentManager(self._engine)
        self.active_agent_versions = ActiveAgentVersionManager(self._engine)
        self.agent_meta = AgentMetaManager(self._engine)
        self.agent_runner_profiles = AgentRunnerProfileManager(self._engine)
        self.prompt_versions = PromptVersionManager(self._engine)
        self.agent_tool_grants = AgentToolGrantManager(self._engine)
        self.agent_sync = AgentSyncManager(self._engine)
        self.agent_config_events = AgentConfigEventManager(self._engine)

        # Workspaces domain
        self.workspaces = WorkspaceManager(self._engine)
        self.workspace_env_docs = WorkspaceEnvDocManager(self._engine)
        self.workspace_env_doc_versions = WorkspaceEnvDocVersionManager(self._engine)
        self.workspace_mcp_overrides = WorkspaceMcpOverrideManager(self._engine)
        self.workspace_mcp_tool_overrides = WorkspaceMcpToolOverrideManager(self._engine)
        self.workspace_mcp_policies = WorkspaceMcpPolicyManager(self._engine)
        self.workspace_host_env_grants = WorkspaceHostEnvGrantManager(self._engine)
        self.workspace_runtime_permissions = WorkspaceRuntimePermissionManager(self._engine)
        self.workspace_subagents = WorkspaceSubagentManager(self._engine)
        self.workenv_templates = WorkenvTemplateManager(self._engine)

        # Resources domain
        self.resources = ResourceManager(self._engine)
        self.resource_versions = ResourceVersionManager(self._engine)
        self.resource_blobs = ResourceBlobManager(self._engine)
        self.active_resource_versions = ActiveResourceVersionManager(self._engine)
        self.shared_resources = SharedResourceManager(self._engine)
        self.agent_prompt_resource_bindings = AgentPromptResourceBindingManager(self._engine)
        self.workspace_file_resource_bindings = WorkspaceFileResourceBindingManager(self._engine)

        # Engines domain
        self.runner_profiles = RunnerProfileManager(self._engine)

        # System domain
        self.api_tokens = ApiTokenManager(self._engine)
        self.settings = SettingManager(self._engine)
        self.host_env_profiles = HostEnvProfileManager(self._engine)
        self.host_env_call_log = HostEnvCallLogManager(self._engine)
        self.mcp_tool_discovery_cache = McpToolDiscoveryCacheManager(self._engine)


@lru_cache(maxsize=None)
def get_database(db_path: str) -> Database:
    """Process-wide ``Database`` per *db_path*.

    Alembic migrations run once per unique path; subsequent calls return
    the same instance.  ``Service`` uses this, as do data-layer callers
    that need manager access without crossing into ``core.service``.
    """
    return Database(Path(db_path))
