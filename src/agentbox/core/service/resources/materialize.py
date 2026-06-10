"""Resource materialization: render, tree, blob reads, and exports."""

from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING, Any, Literal

from jsonschema import Draft202012Validator

from agentbox.core.agents.composition.rendering import render_for_type
from agentbox.core.resources.pydantic_export import schema_to_pydantic

from agentbox.core.service.resources.repo import (
    InvalidResource,
    ResourceNotFound,
    _active_version_or_raise,
    _require_resource,
    _resolve_or_raise,
)

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore

__all__ = [
    "get_blob",
    "render_resource",
    "get_tree",
    "export_pydantic",
    "validate_script_sample",
    "export_zip",
]


def get_blob(resource_id: str, *, store: SessionStore, path: str = "", version_id: str | None = None) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    vid: str = version_id or _active_version_or_raise(store, rid)["id"]
    blob = store.read_repo_blob(vid, path)
    if not blob:
        raise ResourceNotFound(f"blob @ {path!r}")
    return blob


def render_resource(resource_id: str, *, store: SessionStore, version_id: str | None = None) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    resource = _require_resource(store, rid)
    vid: str = version_id or _active_version_or_raise(store, rid)["id"]
    blobs = list(store.iter_repo_blobs(vid))
    return {"resource_id": rid, "version_id": vid, **render_for_type(resource["type"], blobs)}


def get_tree(resource_id: str, *, store: SessionStore, version_id: str | None = None) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    vid: str = version_id or _active_version_or_raise(store, rid)["id"]
    entries = [
        {"relative_path": b.get("relative_path") or "", "size_bytes": b.get("size_bytes"), "mime_type": b.get("mime_type")}
        for b in store.iter_repo_blobs(vid)
    ]
    return {"version_id": vid, "entries": entries}


def export_pydantic(resource_id: str, *, store: SessionStore, class_name: str = "Model", version_id: str | None = None) -> str:
    resource = _require_resource(store, resource_id)
    if resource["type"] != "schema":
        raise InvalidResource("resource is not of type 'schema'")
    vid: str = version_id or _active_version_or_raise(store, resource_id)["id"]
    blob = store.read_repo_blob(vid, "")
    if not blob:
        raise ResourceNotFound("schema blob")
    schema_text = blob.get("content_text") or blob["content"].decode("utf-8")
    try:
        return schema_to_pydantic(schema_text, class_name=class_name)
    except Exception as exc:
        raise InvalidResource(f"export failed: {exc}") from exc


def validate_script_sample(resource_id: str, *, store: SessionStore, sample: Any, direction: Literal["input", "output"] = "input") -> dict:
    resource = _require_resource(store, resource_id)
    if resource["type"] != "script":
        raise InvalidResource("resource is not of type 'script'")
    active = _active_version_or_raise(store, resource_id)
    raw_meta = active.get("metadata_json")
    metadata = json.loads(raw_meta) if raw_meta else {}
    key = "input_schema_resource_id" if direction == "input" else "output_schema_resource_id"
    schema_id = metadata.get(key)
    if not schema_id:
        raise InvalidResource(f"script has no bound {direction} schema")
    schema_active = store.get_active_repo_version(schema_id)
    if not schema_active:
        raise InvalidResource("bound schema has no active version")
    schema_blob = store.read_repo_blob(schema_active["id"], "")
    if not schema_blob:
        raise InvalidResource("schema blob missing")
    schema_doc = json.loads(schema_blob.get("content_text") or schema_blob["content"])
    validator = Draft202012Validator(schema_doc)
    errors = [{"path": list(e.absolute_path), "message": e.message} for e in validator.iter_errors(sample)]
    return {"valid": not errors, "errors": errors, "schema_resource_id": schema_id}


def export_zip(resource_id: str, *, store: SessionStore, version_id: str | None = None) -> tuple[bytes, str]:
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
