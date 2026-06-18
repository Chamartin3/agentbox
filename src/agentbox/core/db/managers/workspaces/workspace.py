"""WorkspaceManager — workspace registry CRUD with cascade delete."""
from __future__ import annotations

from sqlalchemy import delete as sa_delete

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.resources.binding import WorkspaceFileResourceBinding
from agentbox.core.db.models.workspaces.env_doc import WorkspaceEnvDoc, WorkspaceEnvDocVersion
from agentbox.core.db.models.workspaces.host_env_grant import WorkspaceHostEnvGrant
from agentbox.core.db.models.workspaces.mcp_override import (
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
)
from agentbox.core.db.models.workspaces.runtime_permission import WorkspaceRuntimePermission
from agentbox.core.db.models.workspaces.subagent import WorkspaceSubagent
from agentbox.core.db.models.workspaces.template import WorkenvTemplate
from agentbox.core.db.models.workspaces.workspace import Workspace


class WorkspaceManager(Manager[Workspace]):
    """Manager for the ``workspaces`` table with cascade delete support."""

    model = Workspace

    def delete_cascade(self, workspace_name: str) -> None:
        """Delete a workspace and all its satellite records.

        Ported from ``WorkspacesMixin.delete_workspace``. Removes env-docs,
        MCP overrides, subagents, host-env grants, runtime permissions,
        and file resource bindings for the workspace.
        """
        cascade_tables = [
            WorkspaceEnvDocVersion.__table__,
            WorkspaceEnvDoc.__table__,
            WorkspaceMcpToolOverride.__table__,
            WorkspaceMcpOverride.__table__,
            WorkspaceMcpPolicy.__table__,
            WorkspaceSubagent.__table__,
            WorkspaceHostEnvGrant.__table__,
            WorkspaceRuntimePermission.__table__,
            WorkspaceFileResourceBinding.__table__,
            WorkenvTemplate.__table__,
        ]

        with self._engine.begin() as conn:
            for table in cascade_tables:
                if hasattr(table.c, "workspace_id"):
                    conn.execute(
                        sa_delete(table).where(table.c.workspace_id == workspace_name)
                    )
                elif hasattr(table.c, "name") and table.name != "workenv_templates":
                    # workspaces table itself has primary key "name"
                    conn.execute(
                        sa_delete(table).where(table.c.name == workspace_name)
                    )
            # Finally delete the workspace itself
            conn.execute(
                sa_delete(Workspace.__table__).where(getattr(Workspace, "name") == workspace_name)
            )
