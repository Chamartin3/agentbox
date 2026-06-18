"""Shared SQLModel base for every entity model in agentbox.core.db.

``Entity`` is the single superclass for all SQLModel table models. It
provides:

- ``extra="ignore"`` on ``model_config`` so lenient reads don't reject
  unknown columns.
- A common base for ``isinstance`` checks.
- The ``metadata`` class-attribute reference to the shared ``MetaData``
  (inherited from ``SQLModel``).
- TYPE_CHECKING-only stubs for ``__tablename__``, ``__table__``, and
  ``id`` so pyright can type-check model subclasses and the generic
  ``Manager`` without per-site ``# type: ignore``.

Every model in ``models/*`` subclasses ``Entity(table=True)`` to declare
a SQL table row, or ``Entity(table=False)`` when used as a nested
pydantic struct only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from sqlmodel import SQLModel

if TYPE_CHECKING:
    from sqlalchemy import Table


class Entity(SQLModel):
    """Shared base for every agentbox entity model.

    All table models in the catalog subclass ``Entity(table=True)``.
    Nested pydantic shapes subclass ``Entity(table=False)``.

    ``model_config`` is set to ``extra="ignore"`` so that reading from
    the database with a column that doesn't exist on the model doesn't
    raise a validation error — useful for forwards-compatible schema
    evolution.
    """

    if TYPE_CHECKING:
        # SQLAlchemy injects these at runtime; this stub makes pyright
        # accept ``Model.__table__`` access and ``self.model.id`` reads
        # from the generic Manager without per-site ignores.
        # NOTE: __tablename__ is *not* declared here because SQLModel
        # already owns it as a declared_attr; the assignment
        # incompatibility with ``declared_attr[Unknown]`` is a known
        # pyright limitation that must be suppressed per-site.
        __table__: ClassVar[Table]
        # Every table model has a primary key; the generic Manager[T]
        # reads ``model.id`` for ``get(pk)`` and ``create()`` re-fetch.
        # Declaring ``id`` here resolves the ``[union-attr]`` on
        # ``self.model.id`` in the manager base.
        id: Any

    model_config = {"extra": "ignore"}

    # Subclasses should do:
    #   class Foo(Entity, table=True):  ...   # SQL table row
    #   class Bar(Entity, table=False): ...   # nested pydantic struct

    __hash__ = SQLModel.__hash__
