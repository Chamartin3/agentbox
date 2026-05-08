"""JSON Schema importer.

Validates an uploaded payload as a JSON Schema document before persisting
it as a ``schema`` resource. Records the detected dialect and validity
status in ``metadata`` so the UI can flag invalid schemas without re-
parsing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from agentbox.core.constants import ResourceType
from agentbox.core.resources.importers.base import (
    ImporterContext,
    ImporterResult,
    ResourceImporter,
)


@dataclass(frozen=True)
class SchemaImporter(ResourceImporter):
    filename: str
    content: bytes
    import_source: str = "upload"

    def run(self, ctx: ImporterContext) -> ImporterResult:
        try:
            text = self.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Schema file {self.filename!r} is not UTF-8") from exc
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Schema file {self.filename!r} is not valid JSON: {exc}") from exc
        if not isinstance(doc, dict):
            raise ValueError(f"Schema file {self.filename!r} must be a JSON object")

        dialect = doc.get("$schema") or "https://json-schema.org/draft/2020-12/schema"
        is_valid = True
        errors: list[str] = []
        try:
            Draft202012Validator.check_schema(doc)
        except SchemaError as exc:
            is_valid = False
            errors.append(str(exc))

        return ImporterResult(
            blobs=[("", self.content, "application/schema+json", text)],
            import_source=self.import_source,
            source_metadata={"filename": self.filename},
            metadata={
                "schema_dialect": dialect,
                "is_valid": is_valid,
                "validation_errors": errors,
                "title": doc.get("title"),
            },
            suggested_type=ResourceType.SCHEMA,
            suggested_display_name=doc.get("title") or self.filename,
            suggested_description=doc.get("description"),
        )
