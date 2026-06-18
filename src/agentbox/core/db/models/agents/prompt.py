"""PromptVersion model — prompt version history.

Maps to the ``prompt_versions`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class PromptVersion(Entity, table=True):
    """A versioned snapshot of a prompt's content for an agent."""

    __tablename__ = tablename("prompt_versions")

    id: int = Field(default=None, primary_key=True)
    agent_id: str = Field(nullable=False)
    version: int = Field(nullable=False)
    content: str = Field(nullable=False)
    author: str = Field(nullable=False, default="system")
    changelog: str = Field(nullable=False, default="")
    is_draft: int = Field(nullable=False, default=0)
    content_hash: Optional[str] = Field(default=None)
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        Index("idx_prompt_versions_agent", "agent_id", "version", unique=True),
    )
