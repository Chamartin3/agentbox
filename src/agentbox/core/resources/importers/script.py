"""Script importer (Python / shell).

Persists the script body as a ``script`` resource and records the
detected language plus optional input/output schema resource ids in
``metadata`` so agent configs can wire validation around invocations.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath

from agentbox.core.resources.importers.base import (
    ImporterContext,
    ImporterResult,
    ResourceImporter,
)

_EXT_LANG = {
    ".py": "python",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
}


def _detect_language(filename: str) -> str:
    ext = PurePosixPath(filename).suffix.lower()
    lang = _EXT_LANG.get(ext)
    if not lang:
        raise ValueError(
            f"Script file {filename!r} has unsupported extension {ext!r}; "
            f"expected one of {sorted(_EXT_LANG)}"
        )
    return lang


@dataclass(frozen=True)
class ScriptImporter(ResourceImporter):
    filename: str
    content: bytes
    language: str | None = None
    input_schema_resource_id: str | None = None
    output_schema_resource_id: str | None = None
    import_source: str = "upload"

    def run(self, ctx: ImporterContext) -> ImporterResult:
        language = self.language or _detect_language(self.filename)
        if language not in ("python", "shell"):
            raise ValueError(f"Unsupported script language: {language!r}")
        try:
            text = self.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Script file {self.filename!r} is not UTF-8") from exc

        mime, _ = mimetypes.guess_type(self.filename)
        if not mime:
            mime = "text/x-python" if language == "python" else "text/x-shellscript"

        return ImporterResult(
            blobs=[("", self.content, mime, text)],
            import_source=self.import_source,
            source_metadata={"filename": self.filename},
            metadata={
                "language": language,
                "input_schema_resource_id": self.input_schema_resource_id,
                "output_schema_resource_id": self.output_schema_resource_id,
                "line_count": text.count("\n") + 1,
            },
            suggested_type="script",
            suggested_display_name=self.filename,
        )
