"""Pydantic mixin bases for manager-layer domain models.

Layer contract: **managers return pydantic models** built on these mixins,
validated at the DB boundary (``Model.model_validate(dict(row._mapping))``).
**Services return TypedDicts** (see ``envelopes.py`` and the per-domain
``payloads`` modules) whose fields mirror the related domain models.
"""

from __future__ import annotations

from pydantic import BaseModel


class Timestamped(BaseModel):
    """Row shape carrying a creation timestamp (ISO-8601 string)."""

    created_at: str


class Audited(Timestamped):
    """Timestamped row with authorship + changelog audit fields."""

    author: str
    changelog: str


class Versioned(Audited):
    """Audited row that participates in a version sequence."""

    version: int
