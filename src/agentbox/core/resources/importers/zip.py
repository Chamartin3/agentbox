"""Zip-archive importer for folder / skill resources.

Extracts a zip into a temp dir then delegates to ``HostPathImporter`` (or
``SkillImporter`` when the archive contains a ``SKILL.md`` at the root).
Rejects archives with absolute or parent-escaping member names to prevent
zip-slip.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from agentbox.core.resources.importers.base import (
    ImporterContext,
    ImporterResult,
    ResourceImporter,
)
from agentbox.core.resources.importers.host_path import HostPathImporter
from agentbox.core.resources.importers.skill import SkillImporter


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    for member in zf.infolist():
        name = member.filename
        if not name or name.endswith("/"):
            continue
        p = PurePosixPath(name)
        if p.is_absolute() or any(part == ".." for part in p.parts):
            raise ValueError(f"Unsafe zip member path: {name!r}")
        target = dest / Path(*p.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, target.open("wb") as out:
            out.write(src.read())


@dataclass(frozen=True)
class ZipUploadImporter(ResourceImporter):
    filename: str
    content: bytes
    as_skill: bool = False
    import_source: str = "upload"

    def run(self, ctx: ImporterContext) -> ImporterResult:
        try:
            zf = zipfile.ZipFile(io.BytesIO(self.content))
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Not a valid zip archive: {self.filename!r}") from exc

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _safe_extract(zf, root)

            entries = list(root.iterdir())
            single_root = (
                entries[0] if len(entries) == 1 and entries[0].is_dir() else root
            )

            importer_cls = SkillImporter if self.as_skill else HostPathImporter
            importer = importer_cls(root=single_root)
            result = importer.run(ctx)
            return ImporterResult(
                blobs=result.blobs,
                import_source=self.import_source,
                source_metadata={
                    **(result.source_metadata or {}),
                    "filename": self.filename,
                    "extracted_from": "zip",
                },
                metadata=result.metadata,
                suggested_type=result.suggested_type,
                suggested_slug=result.suggested_slug,
                suggested_display_name=result.suggested_display_name
                or single_root.name,
                suggested_description=result.suggested_description,
                suggested_tags=result.suggested_tags,
            )
