"""Generic CRUD manager base for agentbox.core.db.

``Manager[T]`` is the single generic base from which every entity manager
inherits. It provides:

- ``get(pk) -> T | None`` — fetch one by primary key.
- ``all() -> list[T]`` — fetch every row.
- ``find(**filters) -> list[T]`` — filtered query.
- ``create(**fields) -> T`` — insert and return.
- ``update(obj: T) -> T`` — update an existing row from model fields.
- ``delete(obj: T) -> None`` — delete by primary key.

Each method opens its own ``Session`` (internal, never exposed). Subclasses
add custom operations via ``_query(statement)``.

Usage::

    class RunManager(Manager[Run]):
        model = Run

        def finish(self, run_id: str, status: str) -> Run:
            stmt = update(Run).where(Run.id == run_id).values(status=status)
            self._query(stmt)
            return self.get(run_id)

This module is internal. Only ``Database`` instantiates managers.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select, update as sa_update, delete as sa_delete
from agentbox.core.db.base.model import Entity

T = TypeVar("T", bound=Entity)


class Manager(Generic[T]):
    """Generic CRUD manager bound to a SQLAlchemy Engine.

    Every manager subclass **must** set the ``model`` class attribute to
    the SQLModel entity class it manages (e.g. ``model = Run``).
    """

    model: type[T]

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Public generic operations
    # ------------------------------------------------------------------

    def get(self, pk: Any) -> T | None:
        """Fetch one record by primary key, or return None."""
        stmt = select(self.model).where(self.model.id == pk)
        return self._scalar(stmt)

    def all(self) -> list[T]:
        """Return every record."""
        stmt = select(self.model)
        return self._list(stmt)

    def find(self, **filters: Any) -> list[T]:
        """Filtered query: ``find(agent_id="abc", status="ok")``.

        Every keyword argument is matched with ``==`` equality.
        """
        stmt = select(self.model)
        for col, val in filters.items():
            stmt = stmt.where(getattr(self.model, col) == val)
        return self._list(stmt)

    def create(self, **fields: Any) -> T:
        """Create a new record from keyword fields and return the model.

        Raises ``sqlalchemy.exc.IntegrityError`` on constraint violation.
        """
        obj = self.model(**fields)
        with self._engine.begin() as conn:
            conn.execute(self.model.__table__.insert().values(**fields))
        # Return a fresh model instance hydrated from the DB to get defaults.
        return self._scalar(
            select(self.model).where(self.model.id == getattr(obj, "id", None))
        ) or obj

    def update(self, obj: T) -> T:
        """Persist changes to an already-loaded model instance.

        Writes every non-None field back to the DB. The caller must ensure
        ``obj`` has the correct primary key set.
        """
        pk_col = self._pk_col()
        pk_val = getattr(obj, pk_col.name)
        values = {
            c.name: getattr(obj, c.name)
            for c in self.model.__table__.columns
            if c.name != pk_col.name
        }
        stmt = sa_update(self.model).where(pk_col == pk_val).values(**values)
        with self._engine.begin() as conn:
            conn.execute(stmt)
        return obj

    def delete(self, obj: T) -> None:
        """Delete a record by its primary key."""
        pk_col = self._pk_col()
        pk_val = getattr(obj, pk_col.name)
        stmt = sa_delete(self.model).where(pk_col == pk_val)
        with self._engine.begin() as conn:
            conn.execute(stmt)

    # ------------------------------------------------------------------
    # Protected helpers (escape hatch for subclasses)
    # ------------------------------------------------------------------

    def _query(self, stmt: Any) -> Any:
        """Execute a raw SQL statement. Returns the result proxy.

        Subclasses use this for custom operations that can't be expressed
        through the generic interface.
        """
        with self._engine.begin() as conn:
            return conn.execute(stmt)

    def _scalar(self, stmt: Any) -> T | None:
        """Execute a statement and return a single model instance or None."""
        with self._engine.begin() as conn:
            row = conn.execute(stmt).one_or_none()
        if row is None:
            return None
        # If it's a Row (SQLAlchemy Core result), convert to dict.
        data = dict(row._mapping) if hasattr(row, "_mapping") else row
        return self.model(**data)

    def _list(self, stmt: Any) -> list[T]:
        """Execute a statement and return a list of model instances."""
        with self._engine.begin() as conn:
            rows = conn.execute(stmt).all()
        return [
            self.model(**dict(r._mapping)) if hasattr(r, "_mapping") else r
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pk_col(self) -> Any:
        """Return the single primary-key column of the model's table."""
        pks = list(self.model.__table__.primary_key.columns)
        if len(pks) != 1:
            raise NotImplementedError(
                f"{type(self).__name__} does not support composite primary keys. "
                f"Found {len(pks)} PK columns."
            )
        return pks[0]
