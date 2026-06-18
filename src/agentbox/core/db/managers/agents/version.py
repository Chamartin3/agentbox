"""AgentVersion, AgentVersionFile, AgentVersionRating, AgentVersionComment managers."""
from __future__ import annotations

from sqlalchemy import select, update as sa_update

from agentbox.core.db.utils import now_iso
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.version import (
    AgentVersion,
    AgentVersionComment,
    AgentVersionFile,
    AgentVersionRating,
)


class AgentVersionManager(Manager[AgentVersion]):
    """Manager for the ``agent_versions`` table."""

    model = AgentVersion

    def latest_for_agent(self, agent_id: str) -> AgentVersion | None:
        """Return the highest version number for an agent, or None."""
        stmt = (
            select(AgentVersion)
            .where(getattr(AgentVersion, "agent_id") == agent_id)
            .order_by(getattr(AgentVersion, "version").desc())  # sqlalchemy: Column.desc() not in stubs
            .limit(1)
        )
        return self._scalar(stmt)

    def set_active(self, agent_id: str, version_id: int) -> None:
        """Set a version as the active version for an agent."""
        stmt = (
            sa_update(AgentVersion)
            .where(getattr(AgentVersion, "agent_id") == agent_id)
            .values(version_id=version_id, activated_at=now_iso())
        )
        self._query(stmt)


class AgentVersionFileManager(Manager[AgentVersionFile]):
    """Manager for the ``agent_version_files`` table."""
    model = AgentVersionFile


class AgentVersionRatingManager(Manager[AgentVersionRating]):
    """Manager for the ``agent_version_ratings`` table."""
    model = AgentVersionRating


class AgentVersionCommentManager(Manager[AgentVersionComment]):
    """Manager for the ``agent_version_comments`` table."""
    model = AgentVersionComment
