"""Central resource repository API (Plan 01).

Mounted at ``/api/repo-resources`` to avoid colliding with the legacy
``/api/resources`` router (shared_resources: output_schema /
input_schema / user_template / system_fragment).

Resource types covered here: ``document``, ``folder``, ``skill``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.data.store import SessionStore
from agentbox.core.resources.importers.host_path import HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter
from agentbox.core.resources.importers.script import ScriptImporter
from agentbox.core.resources.importers.skill import SkillImporter
from agentbox.core.resources.importers.upload import UploadImporter
from agentbox.core.resources.importers.zip_upload import ZipUploadImporter
from agentbox.core.resources.rendering import render_for_type

router = APIRouter(prefix="/api/repo-resources", tags=["repo-resources"])

ResourceType = Literal["document", "folder", "skill", "schema", "script"]


def _resolve_resource_id(store: SessionStore, id_or_slug: str) -> str | None:
    """Look up a resource by UUID id, slug, or dotted-slug (legacy).

    Returns the canonical resource UUID, or None if not found.
    """
    if not id_or_slug:
        return None
    r = store.get_repo_resource(id_or_slug)
    if r:
        return r["id"]
    r = store.get_repo_resource_by_slug(id_or_slug)
    if r:
        return r["id"]
    if "." in id_or_slug and "/" not in id_or_slug:
        # Legacy ids used dots; new slugs use slashes (agent.X.foo → agent/X/foo).
        # Replace only segments that look like a path separator (preserve dots in
        # final segment like 'output_schema.json').
        candidate = id_or_slug.replace(".", "/")
        r = store.get_repo_resource_by_slug(candidate)
        if r:
            return r["id"]
    return None


# --- request models ---


class CreateResourceBody(BaseModel):
    slug: str
    type: ResourceType
    display_name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class HostPathImportBody(BaseModel):
    path: str
    recursive: bool = True
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    changelog: str = Field(..., min_length=3)
    draft: bool = False
    actor: str | None = None


class PublishBody(BaseModel):
    reason: str = Field(..., min_length=3)
    actor: str | None = None


class RollbackBody(BaseModel):
    target_version: int
    reason: str = Field(..., min_length=3)
    actor: str | None = None


# --- endpoints ---


@router.get("")
def list_resources(
    store: Annotated[SessionStore, Depends(get_store)],
    type: ResourceType | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    return {
        "items": store.list_repo_resources(
            type=type,
            query=q,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        ),
        "total": store.count_repo_resources(
            type=type,
            query=q,
            include_deleted=include_deleted,
        ),
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=201)
def create_resource(
    body: CreateResourceBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return store.create_repo_resource(
            slug=body.slug,
            type=body.type,
            display_name=body.display_name,
            description=body.description,
            tags=body.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{resource_id}")
def get_resource(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    rid = _resolve_resource_id(store, resource_id)
    if rid is None:
        raise HTTPException(status_code=404, detail="resource not found")
    r = store.get_repo_resource(rid)
    active = store.get_active_repo_version(rid) if r and r.get("active_version_id") else None
    return {"resource": r, "active_version": active}


@router.get("/{resource_id}/versions")
def list_versions(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    rid = _resolve_resource_id(store, resource_id)
    if rid is None:
        raise HTTPException(status_code=404, detail="resource not found")
    return {"items": store.list_repo_versions(rid)}


@router.post("/{resource_id}/versions/upload", status_code=201)
async def upload_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
):
    if not store.get_repo_resource(resource_id):
        raise HTTPException(status_code=404, detail="resource not found")
    content = await file.read()
    importer = UploadImporter(
        filename=file.filename or "upload.bin",
        content=content,
        mime_type=file.content_type,
    )
    from agentbox.core.resources.importers.base import ImporterContext

    result = importer.run(ImporterContext(actor=actor, changelog=changelog))
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{resource_id}/versions/from-host-path", status_code=201)
def host_path_version(
    resource_id: str,
    body: HostPathImportBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")

    importer_cls = SkillImporter if resource["type"] == "skill" else HostPathImporter
    importer = importer_cls(
        root=Path(body.path),
        include=tuple(body.include),
        exclude=tuple(body.exclude) or importer_cls.__dataclass_fields__["exclude"].default_factory(),  # type: ignore[attr-defined]
    )
    from agentbox.core.resources.importers.base import ImporterContext

    try:
        result = importer.run(ImporterContext(actor=body.actor, changelog=body.changelog))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return store.import_repo_version(
            resource_id,
            result.blobs,
            import_source=result.import_source,
            changelog=body.changelog,
            source_metadata=result.source_metadata,
            metadata=result.metadata,
            draft=body.draft,
            created_by=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{resource_id}/versions/{version_id}/publish")
def publish_version(
    resource_id: str,
    version_id: str,
    body: PublishBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    v = store.get_repo_version(version_id)
    if not v or v["resource_id"] != resource_id:
        raise HTTPException(status_code=404, detail="version not found")
    try:
        return store.publish_repo_version(
            version_id, reason=body.reason, activated_by=body.actor
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{resource_id}/rollback")
def rollback_resource(
    resource_id: str,
    body: RollbackBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    if not store.get_repo_resource(resource_id):
        raise HTTPException(status_code=404, detail="resource not found")
    try:
        return store.rollback_repo_resource(
            resource_id,
            body.target_version,
            reason=body.reason,
            activated_by=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{resource_id}/blobs")
def get_blob(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    path: str = "",
    version_id: str | None = None,
):
    rid = _resolve_resource_id(store, resource_id)
    if rid is None:
        raise HTTPException(status_code=404, detail="resource not found")
    resource_id = rid
    if version_id is None:
        active = store.get_active_repo_version(resource_id)
        if not active:
            raise HTTPException(status_code=404, detail="no active version")
        version_id = active["id"]
    blob = store.read_repo_blob(version_id, path)
    if not blob:
        raise HTTPException(status_code=404, detail="blob not found")
    return Response(
        content=blob["content"],
        media_type=blob.get("mime_type") or "application/octet-stream",
    )


@router.get("/{resource_id}/render")
def render_resource(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    version_id: str | None = None,
):
    """Return the prompt-embed rendering of a resource version."""
    rid = _resolve_resource_id(store, resource_id)
    if rid is None:
        raise HTTPException(status_code=404, detail="resource not found")
    resource_id = rid
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    if version_id is None:
        active = store.get_active_repo_version(resource_id)
        if not active:
            raise HTTPException(status_code=404, detail="no active version")
        version_id = active["id"]
    blobs = list(store.iter_repo_blobs(version_id))
    return {
        "resource_id": resource_id,
        "version_id": version_id,
        **render_for_type(resource["type"], blobs),
    }


@router.get("/{resource_id}/tree")
def get_tree(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    version_id: str | None = None,
):
    """Return a flat list of blob entries (path, size, mime) for a version."""
    rid = _resolve_resource_id(store, resource_id)
    if rid is None:
        raise HTTPException(status_code=404, detail="resource not found")
    resource_id = rid
    if version_id is None:
        active = store.get_active_repo_version(resource_id)
        if not active:
            raise HTTPException(status_code=404, detail="no active version")
        version_id = active["id"]
    entries = [
        {
            "relative_path": b.get("relative_path") or "",
            "size_bytes": b.get("size_bytes"),
            "mime_type": b.get("mime_type"),
        }
        for b in store.iter_repo_blobs(version_id)
    ]
    return {"version_id": version_id, "entries": entries}


@router.post("/{resource_id}/versions/upload-zip", status_code=201)
async def upload_zip_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
):
    """Zip-upload entrypoint for folder/skill resources."""
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    if resource["type"] not in ("folder", "skill"):
        raise HTTPException(
            status_code=400,
            detail=f"zip upload only valid for folder/skill (got {resource['type']!r})",
        )
    content = await file.read()
    from agentbox.core.resources.importers.base import ImporterContext

    try:
        result = ZipUploadImporter(
            filename=file.filename or "upload.zip",
            content=content,
            as_skill=resource["type"] == "skill",
        ).run(ImporterContext(actor=actor, changelog=changelog))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{resource_id}/versions/upload-schema", status_code=201)
async def upload_schema_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
):
    """Upload a JSON Schema file as a new version of a schema resource."""
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    if resource["type"] != "schema":
        raise HTTPException(
            status_code=400, detail="resource is not of type 'schema'"
        )
    content = await file.read()
    from agentbox.core.resources.importers.base import ImporterContext

    try:
        result = SchemaImporter(
            filename=file.filename or "schema.json", content=content
        ).run(ImporterContext(actor=actor, changelog=changelog))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{resource_id}/versions/upload-script", status_code=201)
async def upload_script_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    language: str | None = None,
    input_schema_resource_id: str | None = None,
    output_schema_resource_id: str | None = None,
    draft: bool = False,
    actor: str | None = None,
):
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    if resource["type"] != "script":
        raise HTTPException(
            status_code=400, detail="resource is not of type 'script'"
        )
    content = await file.read()
    from agentbox.core.resources.importers.base import ImporterContext

    try:
        result = ScriptImporter(
            filename=file.filename or "script",
            content=content,
            language=language,
            input_schema_resource_id=input_schema_resource_id,
            output_schema_resource_id=output_schema_resource_id,
        ).run(ImporterContext(actor=actor, changelog=changelog))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{resource_id}/export/pydantic")
def export_pydantic(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    class_name: str = "Model",
    version_id: str | None = None,
):
    """Render a schema resource as Pydantic v2 source code."""
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    if resource["type"] != "schema":
        raise HTTPException(
            status_code=400, detail="resource is not of type 'schema'"
        )
    if version_id is None:
        active = store.get_active_repo_version(resource_id)
        if not active:
            raise HTTPException(status_code=404, detail="no active version")
        version_id = active["id"]
    blob = store.read_repo_blob(version_id, "")
    if not blob:
        raise HTTPException(status_code=404, detail="schema blob not found")

    from agentbox.core.resources.pydantic_export import schema_to_pydantic

    schema_text = blob.get("content_text") or blob["content"].decode("utf-8")
    try:
        code = schema_to_pydantic(schema_text, class_name=class_name)
    except Exception as exc:  # datamodel-code-generator raises many kinds
        raise HTTPException(status_code=400, detail=f"export failed: {exc}") from exc
    return Response(content=code, media_type="text/x-python")


class ValidateBody(BaseModel):
    sample: dict | list | str | int | float | bool | None
    direction: Literal["input", "output"] = "input"


@router.post("/{resource_id}/validate")
def validate_script_sample(
    resource_id: str,
    body: ValidateBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Validate a sample against the script's input or output schema."""
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    if resource["type"] != "script":
        raise HTTPException(
            status_code=400, detail="resource is not of type 'script'"
        )
    active = store.get_active_repo_version(resource_id)
    if not active:
        raise HTTPException(status_code=404, detail="no active version")

    import json as _json_meta

    raw_meta = active.get("metadata_json")
    metadata = _json_meta.loads(raw_meta) if raw_meta else {}
    key = (
        "input_schema_resource_id"
        if body.direction == "input"
        else "output_schema_resource_id"
    )
    schema_id = metadata.get(key)
    if not schema_id:
        raise HTTPException(
            status_code=400,
            detail=f"script has no bound {body.direction} schema",
        )

    schema_active = store.get_active_repo_version(schema_id)
    if not schema_active:
        raise HTTPException(status_code=400, detail="bound schema has no active version")
    schema_blob = store.read_repo_blob(schema_active["id"], "")
    if not schema_blob:
        raise HTTPException(status_code=400, detail="schema blob missing")

    import json as _json

    from jsonschema import Draft202012Validator

    schema_doc = _json.loads(schema_blob.get("content_text") or schema_blob["content"])
    validator = Draft202012Validator(schema_doc)
    errors = [
        {"path": list(e.absolute_path), "message": e.message}
        for e in validator.iter_errors(body.sample)
    ]
    return {"valid": not errors, "errors": errors, "schema_resource_id": schema_id}


@router.get("/{resource_id}/export/zip")
def export_zip(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    version_id: str | None = None,
):
    """Bundle all blobs of a folder/skill version into a downloadable zip."""
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="resource not found")
    if resource["type"] not in ("folder", "skill"):
        raise HTTPException(
            status_code=400, detail="zip export only supported for folder/skill"
        )
    if version_id is None:
        active = store.get_active_repo_version(resource_id)
        if not active:
            raise HTTPException(status_code=404, detail="no active version")
        version_id = active["id"]

    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for blob in store.iter_repo_blobs(version_id):
            rel = blob.get("relative_path") or ""
            if not rel:
                continue
            zf.writestr(rel, blob["content"])
    filename = f"{resource['slug'].replace(':', '_')}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{resource_id}", status_code=204)
def soft_delete_resource(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    reason: Annotated[str, Query(min_length=3)],
):
    if not store.get_repo_resource(resource_id):
        raise HTTPException(status_code=404, detail="resource not found")
    store.soft_delete_repo_resource(resource_id, reason=reason)
    return Response(status_code=204)
