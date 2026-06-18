"""Helper for declaring SQLModel table metadata without type-ignore.

SQLModel's ``__tablename__`` is typed as ``declared_attr[Unknown]`` at
the class level, which makes ``__tablename__ = "strings"`` trip pyright's
``reportAssignmentType``. ``__table_args__`` has the same issue. These
tiny indirections let every model file declare its table metadata without
a per-site ``# type: ignore``.
"""

from __future__ import annotations

from typing import Any


def tablename(name: str) -> Any:
    """Return a string typed as ``Any`` for use as ``__tablename__``."""
    return name


def tableargs(*args: Any) -> Any:
    """Return args typed as ``Any`` for use as ``__table_args__``."""
    return args
