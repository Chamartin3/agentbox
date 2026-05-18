"""Walk a docker-mounted (or local) directory into a resource version.

Designed to be deterministic: blobs are returned sorted by relative
path, hidden files are skipped by default, and ``include`` / ``exclude``
globs let callers prune large trees.
"""

from __future__ import annotations

import fnmatch
import mimetypes
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from agentbox.core.constants import ResourceType
from agentbox.core.resource.importers.base import (
    ImportedBlob,
    ImporterContext,
    ImporterResult,
    ResourceImporter,
)

TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/yaml")
DEFAULT_EXCLUDES = (
    ".git/*",
    "__pycache__/*",
    "*.pyc",
    ".DS_Store",
    "node_modules/*",
    ".venv/*",
)
MAX_BYTES_PER_BLOB = 50 * 1024 * 1024  # 50 MB cap per blob (plan §Open questions)


def _is_text_mime(mime: str | None) -> bool:
    if not mime:
        return False
    return any(mime.startswith(p) for p in TEXT_MIME_PREFIXES)


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


@dataclass(frozen=True)
class HostPathImporter(ResourceImporter):
    """Read a directory tree as a folder resource.

    For ``type=document`` (single file), point ``root`` directly at the
    file — the importer yields one blob with ``relative_path=""``.
    """

    root: Path
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = field(default_factory=lambda: DEFAULT_EXCLUDES)
    follow_symlinks: bool = False
    include_hidden: bool = False
    import_source: str = "host_path"

    def _read_file(self, path: Path, rel: str) -> ImportedBlob:
        size = path.stat().st_size
        if size > MAX_BYTES_PER_BLOB:
            raise ValueError(
                f"Blob {rel!r} ({size} bytes) exceeds {MAX_BYTES_PER_BLOB} byte cap"
            )
        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        text = None
        if _is_text_mime(mime):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = None
        return (rel, content, mime, text)

    def run(self, ctx: ImporterContext) -> ImporterResult:
        root = self.root.resolve()
        if not root.exists():
            raise FileNotFoundError(f"Host path does not exist: {root}")

        blobs: list[ImportedBlob] = []

        if root.is_file():
            blobs.append(self._read_file(root, ""))
            return ImporterResult(
                blobs=blobs,
                import_source=self.import_source,
                source_metadata={"host_path": str(root), "kind": "file"},
                suggested_type=ResourceType.DOCUMENT,
                suggested_display_name=root.name,
            )

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if not self.include_hidden and any(
                part.startswith(".") for part in rel.split("/")
            ):
                continue
            if _matches_any(rel, self.exclude):
                continue
            if self.include and not _matches_any(rel, self.include):
                continue
            blobs.append(self._read_file(path, rel))

        return ImporterResult(
            blobs=blobs,
            import_source=self.import_source,
            source_metadata={
                "host_path": str(root),
                "kind": "folder",
                "file_count": len(blobs),
            },
            metadata={"file_count": len(blobs)},
            suggested_type=ResourceType.FOLDER,
            suggested_display_name=root.name,
        )
