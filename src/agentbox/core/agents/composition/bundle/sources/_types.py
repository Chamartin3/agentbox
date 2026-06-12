"""Bundle source protocol and shared data types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ReferenceSpec:
    """One entry of ``[[composition.references]]``.

    ``path`` is the original string from the TOML (``shared://...`` or
    bundle-relative). ``heading`` is the optional section heading; when
    missing, the composer falls back to the file stem.
    """

    path: str
    heading: str | None = None


@dataclass(frozen=True)
class OutputSchemaInfo:
    """Resolved output schema (parsed JSON + the relative path it came from)."""

    schema: dict[str, Any]
    relative_path: str


class BundleSource(Protocol):
    """Read interface for a single agent bundle.

    Implementations must surface the same ``composition`` dict shape as the
    TOML on disk so the composer can branch on declared fields without
    needing to know the underlying storage.
    """

    composition: dict[str, Any]

    def references(self) -> list[ReferenceSpec]: ...

    def read_system(self) -> str:
        """Return the raw (un-rendered) system prompt text."""
        ...

    def read_user_template(self) -> str | None:
        """Return the raw user template text, or None when not declared."""
        ...

    def read_reference(self, ref: ReferenceSpec) -> str:
        """Return the raw content for a single reference entry."""
        ...

    def read_output_schema(self) -> OutputSchemaInfo | None:
        """Return the parsed output schema + its relative path, or None."""
        ...

    def read_input_schema(self) -> OutputSchemaInfo | None:
        """Return the parsed input schema + its relative path, or None."""
        ...

    def bundle_files(self) -> dict[str, str]:
        """All files consumed, keyed by their bundle-relative identifier.

        Used to compute the bundle_sha so two sources with identical
        contents produce the same digest.
        """
        ...
