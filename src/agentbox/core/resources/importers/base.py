"""Base classes for resource importers.

An importer turns an external content source (a host directory, an
HTTP upload, a TOML declaration) into a list of ``(relative_path,
content_bytes, mime_type, content_text)`` blob tuples that the
``ResourcesMixin.import_repo_version`` call can persist.

Importers are pure functions of their input — they do not touch the DB
themselves; the store layer does the writes. This keeps importers easy
to test and side-effect-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ImportedBlob = tuple[str, bytes, str | None, str | None]
"""(relative_path, content_bytes, mime_type, content_text)."""


@dataclass(frozen=True)
class ImporterContext:
    """Caller-supplied context shared by all importers.

    Carried into the result so the store layer can persist
    ``source_metadata`` / ``created_by`` without each importer plumbing
    them manually.
    """

    actor: str | None = None
    changelog: str = ""


@dataclass(frozen=True)
class ImporterResult:
    blobs: list[ImportedBlob]
    import_source: str
    source_metadata: dict | None = None
    metadata: dict | None = None
    suggested_slug: str | None = None
    suggested_type: str | None = None
    suggested_display_name: str | None = None
    suggested_description: str | None = None
    suggested_tags: tuple[str, ...] = field(default_factory=tuple)


class ResourceImporter:
    """Importer ABC. Subclasses implement :meth:`run`."""

    import_source: str = "db_only"

    def run(self, ctx: ImporterContext) -> ImporterResult:  # pragma: no cover
        raise NotImplementedError
