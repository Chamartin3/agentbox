"""Integration tests for Phase 1 repo-resources endpoints.

Covers: schema upload, script upload + validate, zip upload, Pydantic
export, and the type filter.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any


def _create(client: Any, slug: str, type_: str, display: str) -> str:
    r = client.post(
        "/api/repo-resources",
        json={"slug": slug, "type": type_, "display_name": display},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _publish_latest(client: Any, rid: str) -> None:
    versions = client.get(f"/api/repo-resources/{rid}/versions").json()["items"]
    vid = versions[0]["id"]
    r = client.post(
        f"/api/repo-resources/{rid}/versions/{vid}/publish",
        json={"reason": "publish for test"},
    )
    assert r.status_code == 200, r.text


def test_schema_upload_and_pydantic_export(client: Any) -> None:
    rid = _create(client, "person-schema", "schema", "Person")
    schema = {
        "title": "Person",
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }
    r = client.post(
        f"/api/repo-resources/{rid}/versions/upload-schema",
        params={"changelog": "first schema"},
        files={"file": ("person.json", json.dumps(schema), "application/json")},
    )
    assert r.status_code == 201, r.text
    _publish_latest(client, rid)

    r = client.get(
        f"/api/repo-resources/{rid}/export/pydantic", params={"class_name": "Person"}
    )
    assert r.status_code == 200, r.text
    assert "class Person" in r.text
    assert "name:" in r.text


def test_script_upload_and_validate(client: Any) -> None:
    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }
    sid = _create(client, "in-schema", "schema", "InputSchema")
    r = client.post(
        f"/api/repo-resources/{sid}/versions/upload-schema",
        params={"changelog": "init"},
        files={"file": ("in.json", json.dumps(schema), "application/json")},
    )
    assert r.status_code == 201
    _publish_latest(client, sid)

    rid = _create(client, "run-script", "script", "run.py")
    r = client.post(
        f"/api/repo-resources/{rid}/versions/upload-script",
        params={"changelog": "first", "input_schema_resource_id": sid},
        files={"file": ("run.py", b"print(1)\n", "text/x-python")},
    )
    assert r.status_code == 201
    _publish_latest(client, rid)

    r = client.post(f"/api/repo-resources/{rid}/validate", json={"sample": {"x": 1}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["errors"] == []

    r = client.post(
        f"/api/repo-resources/{rid}/validate", json={"sample": {"x": "nope"}}
    )
    assert r.status_code == 200
    assert r.json()["valid"] is False


def test_zip_upload_folder(client: Any) -> None:
    rid = _create(client, "docs-folder", "folder", "docs")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", b"alpha")
        zf.writestr("nested/b.txt", b"beta")
    r = client.post(
        f"/api/repo-resources/{rid}/versions/upload-zip",
        params={"changelog": "first zip"},
        files={"file": ("docs.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 201, r.text


def test_type_filter(client: Any) -> None:
    _create(client, "a-doc", "document", "A")
    _create(client, "a-schema", "schema", "S")
    r = client.get("/api/repo-resources", params={"type": "schema"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(it["type"] == "schema" for it in items)
    assert any(it["slug"] == "a-schema" for it in items)


def test_pydantic_export_rejects_non_schema(client: Any) -> None:
    rid = _create(client, "just-doc", "document", "D")
    r = client.get(f"/api/repo-resources/{rid}/export/pydantic")
    assert r.status_code == 400


def test_zip_export_folder(client: Any) -> None:
    rid = _create(client, "bundle-folder", "folder", "Bundle")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.md", b"hello")
        zf.writestr("sub/data.txt", b"data")
    r = client.post(
        f"/api/repo-resources/{rid}/versions/upload-zip",
        params={"changelog": "seed"},
        files={"file": ("b.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 201, r.text
    _publish_latest(client, rid)

    r = client.get(f"/api/repo-resources/{rid}/export/zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
    assert "readme.md" in names
    assert "sub/data.txt" in names


def test_zip_export_rejects_document(client: Any) -> None:
    rid = _create(client, "doc-zipme", "document", "D")
    r = client.get(f"/api/repo-resources/{rid}/export/zip")
    assert r.status_code in (400, 404)  # 404 if no active version, 400 if type mismatch


def test_zip_upload_rejects_document_type(client: Any) -> None:
    rid = _create(client, "txt-doc", "document", "D")
    r = client.post(
        f"/api/repo-resources/{rid}/versions/upload-zip",
        params={"changelog": "nope"},
        files={"file": ("x.zip", b"PK\x05\x06" + b"\x00" * 18, "application/zip")},
    )
    assert r.status_code == 400
