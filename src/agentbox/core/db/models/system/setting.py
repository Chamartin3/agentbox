"""Setting model — application settings key-value store.

Maps to the ``settings`` table. Uses a composite primary key of
(section, key).
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class Setting(Entity, table=True):
    """A single application setting within a section."""

    __tablename__ = tablename("settings")

    section: str = Field(primary_key=True)
    key: str = Field(primary_key=True)
    value_json: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)
    updated_by: Optional[str] = Field(default=None)
