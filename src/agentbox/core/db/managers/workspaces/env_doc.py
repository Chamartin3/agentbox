"""WorkspaceEnvDoc and WorkspaceEnvDocVersion managers."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.env_doc import WorkspaceEnvDoc, WorkspaceEnvDocVersion


class WorkspaceEnvDocManager(Manager[WorkspaceEnvDoc]):
    """Manager for the ``workspace_env_docs`` table."""
    model = WorkspaceEnvDoc


class WorkspaceEnvDocVersionManager(Manager[WorkspaceEnvDocVersion]):
    """Manager for the ``workspace_env_doc_versions`` table."""
    model = WorkspaceEnvDocVersion
