"""Resource importer dispatch service operations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.resources.importers.base import ImporterContext
from agentbox.core.resources.importers.host_path import HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter
from agentbox.core.resources.importers.script import ScriptImporter
from agentbox.core.resources.importers.skill import SkillImporter
from agentbox.core.resources.importers.upload import UploadImporter
from agentbox.core.resources.importers.zip import ZipUploadImporter

from agentbox.core.service.resources.repo import InvalidResource, _require_resource

if TYPE_CHECKING:
    from agentbox.core.db import SessionStore

__all__ = [
    "import_upload_version",
    "import_host_path_version",
    "import_zip_version",
    "import_schema_version",
    "import_script_version",
]


def _import_with(store: SessionStore, resource_id: str, importer: Any, *, changelog: str, draft: bool, actor: str | None) -> dict:
    try:
        result = importer.run(ImporterContext(actor=actor, changelog=changelog))
    except (FileNotFoundError, ValueError) as exc:
        raise InvalidResource(str(exc)) from exc
    try:
        return store.import_repo_version(
            resource_id, result.blobs, import_source=result.import_source,
            changelog=changelog, source_metadata=result.source_metadata,
            metadata=result.metadata, draft=draft, created_by=actor,
        )
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


def import_upload_version(resource_id: str, *, store: SessionStore, filename: str, content: bytes, mime_type: str | None, changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    _require_resource(store, resource_id)
    importer = UploadImporter(filename=filename or "upload.bin", content=content, mime_type=mime_type)
    return _import_with(store, resource_id, importer, changelog=changelog, draft=draft, actor=actor)


def import_host_path_version(resource_id: str, *, store: SessionStore, path: str, include: list[str], exclude: list[str], changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    resource = _require_resource(store, resource_id)
    importer_cls = SkillImporter if resource["type"] == "skill" else HostPathImporter
    default_exclude = importer_cls.__dataclass_fields__["exclude"].default_factory()
    importer = importer_cls(root=Path(path), include=tuple(include), exclude=tuple(exclude) or default_exclude)
    return _import_with(store, resource_id, importer, changelog=changelog, draft=draft, actor=actor)


def import_zip_version(resource_id: str, *, store: SessionStore, filename: str, content: bytes, changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] not in ("folder", "skill"):
        raise InvalidResource(f"zip upload only valid for folder/skill (got {resource['type']!r})")
    importer = ZipUploadImporter(filename=filename or "upload.zip", content=content, as_skill=resource["type"] == "skill")
    return _import_with(store, resource_id, importer, changelog=changelog, draft=draft, actor=actor)


def import_schema_version(resource_id: str, *, store: SessionStore, filename: str, content: bytes, changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] != "schema":
        raise InvalidResource("resource is not of type 'schema'")
    importer = SchemaImporter(filename=filename or "schema.json", content=content)
    return _import_with(store, resource_id, importer, changelog=changelog, draft=draft, actor=actor)


def import_script_version(resource_id: str, *, store: SessionStore, filename: str, content: bytes, changelog: str, language: str | None = None, input_schema_resource_id: str | None = None, output_schema_resource_id: str | None = None, draft: bool = False, actor: str | None = None) -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] != "script":
        raise InvalidResource("resource is not of type 'script'")
    importer = ScriptImporter(filename=filename or "script", content=content, language=language, input_schema_resource_id=input_schema_resource_id, output_schema_resource_id=output_schema_resource_id)
    return _import_with(store, resource_id, importer, changelog=changelog, draft=draft, actor=actor)
