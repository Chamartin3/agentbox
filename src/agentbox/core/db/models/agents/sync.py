"""AgentSync model — manifest-to-DB sync metadata.

Maps to the ``agent_sync`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class AgentSync(Entity, table=True):
    """Sync tracking metadata for an agent definition between manifest and DB."""

    __tablename__ = tablename("agent_sync")

    agent_id: str = Field(primary_key=True)
    proxy_path: Optional[str] = Field(default=None)
    sync_mode: str = Field(nullable=False, default="manual")
    sync_policy: str = Field(nullable=False, default="db_wins")
    last_file_hash: Optional[str] = Field(default=None)
    last_file_mtime: Optional[str] = Field(default=None)
    last_sync_at: Optional[str] = Field(default=None)
