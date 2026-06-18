"""WorkenvTemplate model — work environment template presets.

Maps to the ``workenv_templates`` table. Stores complete WorkenvConfig
presets referenced during workspace generation.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class WorkenvTemplate(Entity, table=True):
    """A named work environment configuration template."""

    __tablename__ = tablename("workenv_templates")

    name: str = Field(primary_key=True)
    description: Optional[str] = Field(default=None)
    engine: str = Field(nullable=False, default="claude_code")
    config_json: str = Field(nullable=False, sa_type=JSON)
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)
