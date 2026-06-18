"""Shared SQLAlchemy ``MetaData`` for the agentbox core.db package.

Every SQLModel model in ``agentbox.core.db`` binds to this single instance
so Alembic (and metadata.create_all) see the full schema in one place.

We reuse the default ``SQLModel.metadata`` — SQLModel sets this to a shared
``MetaData`` instance automatically. Alembic sees the same metadata
collection that ``Entity.metadata`` points to.

External code MUST NOT import from this module. The ``core.db`` façade is
the only public surface.
"""
from __future__ import annotations

from sqlmodel import SQLModel

# SQLModel creates its own MetaData; reuse it so Alembic sees all tables.
metadata = SQLModel.metadata

__all__ = ["metadata"]
