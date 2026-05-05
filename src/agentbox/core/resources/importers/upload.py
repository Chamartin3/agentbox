"""HTTP upload importer.

The API route reads bytes off the request stream and hands them here
so the same import_repo_version code path is used for upload and
host-path imports.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass

from agentbox.core.resources.importers.base import (
    ImporterContext,
    ImporterResult,
    ResourceImporter,
)
from agentbox.core.resources.importers.host_path import _is_text_mime


@dataclass(frozen=True)
class UploadImporter(ResourceImporter):
    filename: str
    content: bytes
    mime_type: str | None = None
    import_source: str = "upload"

    def run(self, ctx: ImporterContext) -> ImporterResult:
        mime = self.mime_type
        if not mime:
            mime, _ = mimetypes.guess_type(self.filename)
        text = None
        if _is_text_mime(mime):
            try:
                text = self.content.decode("utf-8")
            except UnicodeDecodeError:
                text = None
        return ImporterResult(
            blobs=[("", self.content, mime, text)],
            import_source=self.import_source,
            source_metadata={"filename": self.filename, "mime": mime},
            suggested_type="document",
            suggested_display_name=self.filename,
        )
