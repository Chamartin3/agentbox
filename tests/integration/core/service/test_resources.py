"""Tests for ``core.service.resources``.

Pin the domain error surface and basic CRUD round-trip for the repo
resource service. The importer plumbing and pydantic export use real
implementations; tests stick to small text blobs to stay fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.db import SessionStore
from agentbox.core.service import resources as res_service
from agentbox.core.service.resources import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
)


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "agentbox.sqlite")


def _create(store: SessionStore, slug: str = "doc/a", rtype: str = "document") -> dict:
    return res_service.create_resource(
        store=store,
        slug=slug,
        type=rtype,  # type: ignore[arg-type]
        display_name=slug,
    )


# ---------------------------------------------------------------------------
# resolve_resource_id
# ---------------------------------------------------------------------------


def test_resolve_resource_id_returns_none_for_unknown(store: SessionStore) -> None:
    assert res_service.resolve_resource_id(store, "nope") is None


def test_resolve_resource_id_finds_by_slug(store: SessionStore) -> None:
    row = _create(store)
    assert res_service.resolve_resource_id(store, "doc/a") == row["id"]


def test_resolve_resource_id_finds_by_legacy_dotted_slug(store: SessionStore) -> None:
    row = _create(store, slug="agent/X/foo")
    assert res_service.resolve_resource_id(store, "agent.X.foo") == row["id"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_get_resource_raises_when_missing(store: SessionStore) -> None:
    with pytest.raises(ResourceNotFound):
        res_service.get_resource("missing", store=store)


def test_get_resource_returns_envelope(store: SessionStore) -> None:
    _create(store)
    payload = res_service.get_resource("doc/a", store=store)
    assert set(payload) == {"resource", "active_version"}
    assert payload["resource"]["slug"] == "doc/a"
    assert payload["active_version"] is None


def test_update_resource_raises_when_missing(store: SessionStore) -> None:
    with pytest.raises(ResourceNotFound):
        res_service.update_resource("missing", store=store, display_name="x")


def test_update_resource_changes_display_name(store: SessionStore) -> None:
    _create(store)
    out = res_service.update_resource("doc/a", store=store, display_name="renamed")
    assert out["display_name"] == "renamed"


def test_create_resource_duplicate_slug_raises(store: SessionStore) -> None:
    _create(store)
    # store-level uniqueness rejection bubbles as IntegrityError; service
    # only translates ValueError. Pin the current contract.
    with pytest.raises(Exception):
        _create(store)


def test_list_resources_envelope(store: SessionStore) -> None:
    _create(store)
    out = res_service.list_resources(store=store)
    assert set(out) == {"items", "total", "limit", "offset"}
    assert out["total"] == 1


# ---------------------------------------------------------------------------
# Versions / blobs / render / tree
# ---------------------------------------------------------------------------


def test_list_versions_empty_for_new_resource(store: SessionStore) -> None:
    _create(store)
    out = res_service.list_versions("doc/a", store=store)
    assert out == {"items": []}


def test_get_blob_raises_no_active_version(store: SessionStore) -> None:
    _create(store)
    with pytest.raises(NoActiveVersion):
        res_service.get_blob("doc/a", store=store)


def test_render_resource_raises_no_active_version(store: SessionStore) -> None:
    _create(store)
    with pytest.raises(NoActiveVersion):
        res_service.render_resource("doc/a", store=store)


def test_get_tree_raises_no_active_version(store: SessionStore) -> None:
    _create(store)
    with pytest.raises(NoActiveVersion):
        res_service.get_tree("doc/a", store=store)


# ---------------------------------------------------------------------------
# Export / soft delete
# ---------------------------------------------------------------------------


def test_export_pydantic_rejects_non_schema(store: SessionStore) -> None:
    row = _create(store)
    with pytest.raises(InvalidResource):
        res_service.export_pydantic(row["id"], store=store)


def test_export_zip_rejects_non_folder_or_skill(store: SessionStore) -> None:
    row = _create(store)
    with pytest.raises(InvalidResource):
        res_service.export_zip(row["id"], store=store)


def test_validate_script_sample_rejects_non_script(store: SessionStore) -> None:
    row = _create(store)
    with pytest.raises(InvalidResource):
        res_service.validate_script_sample(row["id"], store=store, sample={})


def test_soft_delete_resource_raises_when_missing(store: SessionStore) -> None:
    with pytest.raises(ResourceNotFound):
        res_service.soft_delete_resource("missing", store=store, reason="bye")


def test_soft_delete_resource_marks_deleted(store: SessionStore) -> None:
    row = _create(store)
    res_service.soft_delete_resource(row["id"], store=store, reason="cleanup")
    listed = res_service.list_resources(store=store)
    assert listed["total"] == 0


# ---------------------------------------------------------------------------
# Import / publish / rollback domain errors
# ---------------------------------------------------------------------------


def test_publish_unknown_version_raises_not_found(store: SessionStore) -> None:
    _create(store)
    with pytest.raises(ResourceNotFound):
        res_service.publish_version(
            "doc/a", "no-such", store=store, reason="ship it"
        )


def test_rollback_unknown_resource_raises(store: SessionStore) -> None:
    with pytest.raises(ResourceNotFound):
        res_service.rollback_resource(
            "missing", store=store, target_version=1, reason="rb"
        )


def test_import_upload_version_missing_resource_raises(store: SessionStore) -> None:
    with pytest.raises(ResourceNotFound):
        res_service.import_upload_version(
            "missing",
            store=store,
            filename="x.txt",
            content=b"x",
            mime_type="text/plain",
            changelog="add",
        )


def test_import_zip_rejects_non_folder_or_skill(store: SessionStore) -> None:
    _create(store)  # type='document'
    res = res_service.get_resource("doc/a", store=store)
    resource_id = res["resource"]["id"]
    with pytest.raises(InvalidResource):
        res_service.import_zip_version(
            resource_id,
            store=store,
            filename="bundle.zip",
            content=b"zip",
            changelog="add",
        )
