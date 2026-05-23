"""Service layer for the central resource repository.

Wraps the repo-resource CRUD, importer dispatch, version publishing,
blob/render/tree reads, and export helpers that used to live in
``api/resources/repo.py``. Routes become a thin transport adapter:
parse → call → map domain errors to HTTP.

Dependency injection is explicit (``store``) so this module has no
import of FastAPI deps. MCP tools and CLI consumers can reuse the
same use-cases.

Domain errors raised here:

* :class:`ResourceNotFound` — unknown resource id/slug or version.
* :class:`InvalidResource` — bad type for the requested operation
  (e.g. zip export on a schema), bad input, importer rejections.
* :class:`NoActiveVersion` — resource has no active version when one
  is required (render, tree, blob default).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from agentbox.core.constants import ResourceType
from agentbox.core.prompt.rendering import render_for_type
from agentbox.core.resource.importers.base import ImporterContext
from agentbox.core.resource.importers.host_path import HostPathImporter
from agentbox.core.resource.importers.schema import SchemaImporter
from agentbox.core.resource.importers.script import ScriptImporter
from agentbox.core.resource.importers.skill import SkillImporter
from agentbox.core.resource.importers.upload import UploadImporter
from agentbox.core.resource.importers.zip_upload import ZipUploadImporter

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore

__all__ = [
    "ResourceNotFound",
    "InvalidResource",
    "NoActiveVersion",
    "resolve_resource_id",
    "list_resources",
    "create_resource",
    "get_resource",
    "update_resource",
    "list_versions",
    "import_upload_version",
    "import_host_path_version",
    "import_zip_version",
    "import_schema_version",
    "import_script_version",
    "publish_version",
    "rollback_resource",
    "get_blob",
    "render_resource",
    "get_tree",
    "export_pydantic",
    "validate_script_sample",
    "export_zip",
    "soft_delete_resource",
]


class ResourceNotFound(LookupError):
    def __init__(self, resource_id: str) -> None:
        super().__init__(f"resource {resource_id!r} not found")
        self.resource_id = resource_id


class InvalidResource(ValueError):
    """Resource exists but the requested operation is invalid for it."""


class NoActiveVersion(LookupError):
    def __init__(self, resource_id: str) -> None:
        super().__init__(f"no active version for resource {resource_id!r}")
        self.resource_id = resource_id


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def resolve_resource_id(store: SessionStore, id_or_slug: str) -> str | None:
    """Look up a resource by UUID, slug, or legacy dotted-slug."""
    if not id_or_slug:
        return None
    r = store.get_repo_resource(id_or_slug)
    if r:
        return r["id"]
    r = store.get_repo_resource_by_slug(id_or_slug)
    if r:
        return r["id"]
    if "." in id_or_slug and "/" not in id_or_slug:
        candidate = id_or_slug.replace(".", "/")
        r = store.get_repo_resource_by_slug(candidate)
        if r:
            return r["id"]
    return None


def _resolve_or_raise(store: SessionStore, id_or_slug: str) -> str:
    rid = resolve_resource_id(store, id_or_slug)
    if rid is None:
        raise ResourceNotFound(id_or_slug)
    return rid


def _active_version_or_raise(store: SessionStore, resource_id: str) -> dict:
    active = store.get_active_repo_version(resource_id)
    if not active:
        raise NoActiveVersion(resource_id)
    return active


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_resources(
    *,
    store: SessionStore,
    type: ResourceType | None = None,
    query: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return {
        "items": store.list_repo_resources(
            type=type,
            query=query,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        ),
        "total": store.count_repo_resources(
            type=type, query=query, include_deleted=include_deleted
        ),
        "limit": limit,
        "offset": offset,
    }


def create_resource(
    *,
    store: SessionStore,
    slug: str,
    type: ResourceType,
    display_name: str,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    try:
        return store.create_repo_resource(
            slug=slug,
            type=type,
            display_name=display_name,
            description=description,
            tags=tags or [],
        )
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


def get_resource(resource_id: str, *, store: SessionStore) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    r = store.get_repo_resource(rid)
    active = (
        store.get_active_repo_version(rid) if r and r.get("active_version_id") else None
    )
    return {"resource": r, "active_version": active}


def update_resource(
    resource_id: str,
    *,
    store: SessionStore,
    display_name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    updated = store.update_repo_resource(
        rid, display_name=display_name, description=description, tags=tags
    )
    if updated is None:
        raise ResourceNotFound(resource_id)
    return updated


def list_versions(resource_id: str, *, store: SessionStore) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    return {"items": store.list_repo_versions(rid)}


# ---------------------------------------------------------------------------
# Importers
# ---------------------------------------------------------------------------


def _import_with(
    store: SessionStore,
    resource_id: str,
    importer: Any,
    *,
    changelog: str,
    draft: bool,
    actor: str | None,
) -> dict:
    try:
        result = importer.run(ImporterContext(actor=actor, changelog=changelog))
    except (FileNotFoundError, ValueError) as exc:
        raise InvalidResource(str(exc)) from exc
    try:
        return store.import_repo_version(
            resource_id,
            result.blobs,
            import_source=result.import_source,
            changelog=changelog,
            source_metadata=result.source_metadata,
            metadata=result.metadata,
            draft=draft,
            created_by=actor,
        )
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


def _require_resource(store: SessionStore, resource_id: str) -> dict:
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise ResourceNotFound(resource_id)
    return resource


def import_upload_version(
    resource_id: str,
    *,
    store: SessionStore,
    filename: str,
    content: bytes,
    mime_type: str | None,
    changelog: str,
    draft: bool = False,
    actor: str | None = None,
) -> dict:
    _require_resource(store, resource_id)
    importer = UploadImporter(
        filename=filename or "upload.bin",
        content=content,
        mime_type=mime_type,
    )
    return _import_with(
        store, resource_id, importer, changelog=changelog, draft=draft, actor=actor
    )


def import_host_path_version(
    resource_id: str,
    *,
    store: SessionStore,
    path: str,
    include: list[str],
    exclude: list[str],
    changelog: str,
    draft: bool = False,
    actor: str | None = None,
) -> dict:
    resource = _require_resource(store, resource_id)
    importer_cls = SkillImporter if resource["type"] == "skill" else HostPathImporter
    default_exclude = importer_cls.__dataclass_fields__[  # type: ignore[attr-defined]
        "exclude"
    ].default_factory()
    importer = importer_cls(
        root=Path(path),
        include=tuple(include),
        exclude=tuple(exclude) or default_exclude,
    )
    return _import_with(
        store, resource_id, importer, changelog=changelog, draft=draft, actor=actor
    )


def import_zip_version(
    resource_id: str,
    *,
    store: SessionStore,
    filename: str,
    content: bytes,
    changelog: str,
    draft: bool = False,
    actor: str | None = None,
) -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] not in ("folder", "skill"):
        raise InvalidResource(
            f"zip upload only valid for folder/skill (got {resource['type']!r})"
        )
    importer = ZipUploadImporter(
        filename=filename or "upload.zip",
        content=content,
        as_skill=resource["type"] == "skill",
    )
    return _import_with(
        store, resource_id, importer, changelog=changelog, draft=draft, actor=actor
    )


def import_schema_version(
    resource_id: str,
    *,
    store: SessionStore,
    filename: str,
    content: bytes,
    changelog: str,
    draft: bool = False,
    actor: str | None = None,
) -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] != "schema":
        raise InvalidResource("resource is not of type 'schema'")
    importer = SchemaImporter(filename=filename or "schema.json", content=content)
    return _import_with(
        store, resource_id, importer, changelog=changelog, draft=draft, actor=actor
    )


def import_script_version(
    resource_id: str,
    *,
    store: SessionStore,
    filename: str,
    content: bytes,
    changelog: str,
    language: str | None = None,
    input_schema_resource_id: str | None = None,
    output_schema_resource_id: str | None = None,
    draft: bool = False,
    actor: str | None = None,
) -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] != "script":
        raise InvalidResource("resource is not of type 'script'")
    importer = ScriptImporter(
        filename=filename or "script",
        content=content,
        language=language,
        input_schema_resource_id=input_schema_resource_id,
        output_schema_resource_id=output_schema_resource_id,
    )
    return _import_with(
        store, resource_id, importer, changelog=changelog, draft=draft, actor=actor
    )


# ---------------------------------------------------------------------------
# Publish / rollback
# ---------------------------------------------------------------------------


def publish_version(
    resource_id: str,
    version_id: str,
    *,
    store: SessionStore,
    reason: str,
    actor: str | None = None,
) -> dict:
    v = store.get_repo_version(version_id)
    if not v or v["resource_id"] != resource_id:
        raise ResourceNotFound(version_id)
    try:
        return store.publish_repo_version(
            version_id, reason=reason, activated_by=actor
        )
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


def rollback_resource(
    resource_id: str,
    *,
    store: SessionStore,
    target_version: int,
    reason: str,
    actor: str | None = None,
) -> dict:
    _require_resource(store, resource_id)
    try:
        return store.rollback_repo_resource(
            resource_id, target_version, reason=reason, activated_by=actor
        )
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


# ---------------------------------------------------------------------------
# Blob / render / tree
# ---------------------------------------------------------------------------


def get_blob(
    resource_id: str,
    *,
    store: SessionStore,
    path: str = "",
    version_id: str | None = None,
) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    vid: str = version_id or _active_version_or_raise(store, rid)["id"]
    blob = store.read_repo_blob(vid, path)
    if not blob:
        raise ResourceNotFound(f"blob @ {path!r}")
    return blob


def render_resource(
    resource_id: str,
    *,
    store: SessionStore,
    version_id: str | None = None,
) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    resource = _require_resource(store, rid)
    vid: str = version_id or _active_version_or_raise(store, rid)["id"]
    blobs = list(store.iter_repo_blobs(vid))
    return {
        "resource_id": rid,
        "version_id": vid,
        **render_for_type(resource["type"], blobs),
    }


def get_tree(
    resource_id: str,
    *,
    store: SessionStore,
    version_id: str | None = None,
) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    vid: str = version_id or _active_version_or_raise(store, rid)["id"]
    entries = [
        {
            "relative_path": b.get("relative_path") or "",
            "size_bytes": b.get("size_bytes"),
            "mime_type": b.get("mime_type"),
        }
        for b in store.iter_repo_blobs(vid)
    ]
    return {"version_id": vid, "entries": entries}


# ---------------------------------------------------------------------------
# Exports / validate
# ---------------------------------------------------------------------------


def export_pydantic(
    resource_id: str,
    *,
    store: SessionStore,
    class_name: str = "Model",
    version_id: str | None = None,
) -> str:
    """Return Pydantic v2 source code for a schema resource."""
    resource = _require_resource(store, resource_id)
    if resource["type"] != "schema":
        raise InvalidResource("resource is not of type 'schema'")
    vid: str = version_id or _active_version_or_raise(store, resource_id)["id"]
    blob = store.read_repo_blob(vid, "")
    if not blob:
        raise ResourceNotFound("schema blob")
    from agentbox.core.resource.pydantic_export import schema_to_pydantic

    schema_text = blob.get("content_text") or blob["content"].decode("utf-8")
    try:
        return schema_to_pydantic(schema_text, class_name=class_name)
    except Exception as exc:
        raise InvalidResource(f"export failed: {exc}") from exc


def validate_script_sample(
    resource_id: str,
    *,
    store: SessionStore,
    sample: Any,
    direction: Literal["input", "output"] = "input",
) -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] != "script":
        raise InvalidResource("resource is not of type 'script'")
    active = _active_version_or_raise(store, resource_id)

    raw_meta = active.get("metadata_json")
    metadata = json.loads(raw_meta) if raw_meta else {}
    key = (
        "input_schema_resource_id"
        if direction == "input"
        else "output_schema_resource_id"
    )
    schema_id = metadata.get(key)
    if not schema_id:
        raise InvalidResource(f"script has no bound {direction} schema")

    schema_active = store.get_active_repo_version(schema_id)
    if not schema_active:
        raise InvalidResource("bound schema has no active version")
    schema_blob = store.read_repo_blob(schema_active["id"], "")
    if not schema_blob:
        raise InvalidResource("schema blob missing")

    from jsonschema import Draft202012Validator

    schema_doc = json.loads(schema_blob.get("content_text") or schema_blob["content"])
    validator = Draft202012Validator(schema_doc)
    errors = [
        {"path": list(e.absolute_path), "message": e.message}
        for e in validator.iter_errors(sample)
    ]
    return {"valid": not errors, "errors": errors, "schema_resource_id": schema_id}


def export_zip(
    resource_id: str,
    *,
    store: SessionStore,
    version_id: str | None = None,
) -> tuple[bytes, str]:
    """Return ``(zip_bytes, filename)`` for a folder/skill version."""
    resource = _require_resource(store, resource_id)
    if resource["type"] not in ("folder", "skill"):
        raise InvalidResource("zip export only supported for folder/skill")
    vid: str = version_id or _active_version_or_raise(store, resource_id)["id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for blob in store.iter_repo_blobs(vid):
            rel = blob.get("relative_path") or ""
            if not rel:
                continue
            zf.writestr(rel, blob["content"])
    filename = f"{resource['slug'].replace(':', '_')}.zip"
    return buf.getvalue(), filename


def soft_delete_resource(
    resource_id: str, *, store: SessionStore, reason: str
) -> None:
    _require_resource(store, resource_id)
    store.soft_delete_repo_resource(resource_id, reason=reason)
