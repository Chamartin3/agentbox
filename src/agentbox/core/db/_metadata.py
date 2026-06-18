"""Shared SQLAlchemy ``MetaData`` for the agentbox data package.

Every table in ``agentbox.core.db`` binds to this single instance so
Alembic and ``metadata.create_all(engine)`` see the full schema in one
place. This module is the seam that lets schema definitions split across
domain packages without fragmenting ``MetaData``.

Import ``metadata`` here from any module that defines a ``Table``.
External code should import ``metadata`` from ``agentbox.core.db`` —
not from this private module — because the façade is the stable surface.
"""

from __future__ import annotations

from sqlalchemy import MetaData

metadata: MetaData = MetaData()

__all__ = ["metadata"]
