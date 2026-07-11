"""Tests for ``core.service.resources``.

Pin the domain error surface and basic CRUD round-trip for the repo
resource service. The importer plumbing and pydantic export use real
implementations; tests stick to small text blobs to stay fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data.constants import ResourceType
from agentbox.core.data import RepoResourceRow
from agentbox.core.db.database import Database
from agentbox.core.service.resources import ResourceService
from agentbox.core.service.resources import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
)


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


def _create(store: Database, slug: str = "doc/a", rtype: ResourceType = ResourceType.DOCUMENT) -> RepoResourceRow:
    return ResourceService().create_resource(
        slug=slug,
        type=rtype,
        display_name=slug,
    )


# ---------------------------------------------------------------------------
# resolve_resource_id
# ---------------------------------------------------------------------------


def test_resolve_resource_id_returns_none_for_unknown(store: Database) -> None:
    assert ResourceService().resolve_resource_id("nope") is None


def test_resolve_resource_id_finds_by_slug(store: Database) -> None:
    row = _create(store)
    assert ResourceService().resolve_resource_id("doc/a") == row["id"]


def test_resolve_resource_id_finds_by_legacy_dotted_slug(store: Database) -> None:
    row = _create(store, slug="agent/X/foo")
    assert ResourceService().resolve_resource_id("agent.X.foo") == row["id"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_get_resource_raises_when_missing(store: Database) -> None:
    with pytest.raises(ResourceNotFound):
        ResourceService().get_resource("missing")


def test_get_resource_returns_envelope(store: Database) -> None:
    _create(store)
    payload = ResourceService().get_resource("doc/a")
    assert set(payload) == {"resource", "active_version"}
    assert payload["resource"]["slug"] == "doc/a"
    assert payload["active_version"] is None


def test_update_resource_raises_when_missing(store: Database) -> None:
    with pytest.raises(ResourceNotFound):
        ResourceService().update_resource("missing", display_name="x")


def test_update_resource_changes_display_name(store: Database) -> None:
    _create(store)
    out = ResourceService().update_resource("doc/a", display_name="renamed")
    assert out["display_name"] == "renamed"


def test_create_resource_duplicate_slug_raises(store: Database) -> None:
    _create(store)
    # store-level uniqueness rejection bubbles as IntegrityError; service
    # only translates ValueError. Pin the current contract.
    with pytest.raises(Exception):
        _create(store)


def test_list_resources_envelope(store: Database) -> None:
    _create(store)
    out = ResourceService().list_resources()
    assert set(out) == {"items", "total", "limit", "offset"}
    assert out["total"] == 1


# ---------------------------------------------------------------------------
# Versions / blobs / render / tree
# ---------------------------------------------------------------------------


def test_list_versions_empty_for_new_resource(store: Database) -> None:
    _create(store)
    out = ResourceService().list_versions("doc/a")
    assert out == {"items": []}


def test_get_blob_raises_no_active_version(store: Database) -> None:
    _create(store)
    with pytest.raises(NoActiveVersion):
        ResourceService().get_blob("doc/a")


def test_render_resource_raises_no_active_version(store: Database) -> None:
    _create(store)
    with pytest.raises(NoActiveVersion):
        ResourceService().render_resource("doc/a")


def test_get_tree_raises_no_active_version(store: Database) -> None:
    _create(store)
    with pytest.raises(NoActiveVersion):
        ResourceService().get_tree("doc/a")


# ---------------------------------------------------------------------------
# Export / soft delete
# ---------------------------------------------------------------------------


def test_export_pydantic_rejects_non_schema(store: Database) -> None:
    row = _create(store)
    with pytest.raises(InvalidResource):
        ResourceService().export_pydantic(row["id"])


def test_export_zip_rejects_non_folder_or_skill(store: Database) -> None:
    row = _create(store)
    with pytest.raises(InvalidResource):
        ResourceService().export_zip(row["id"])


def test_validate_script_sample_rejects_non_script(store: Database) -> None:
    row = _create(store)
    with pytest.raises(InvalidResource):
        ResourceService().validate_script_sample(row["id"], sample={})


def test_soft_delete_resource_raises_when_missing(store: Database) -> None:
    with pytest.raises(ResourceNotFound):
        ResourceService().soft_delete_resource("missing", reason="bye")


def test_soft_delete_resource_marks_deleted(store: Database) -> None:
    row = _create(store)
    ResourceService().soft_delete_resource(row["id"], reason="cleanup")
    listed = ResourceService().list_resources()
    assert listed["total"] == 0


# ---------------------------------------------------------------------------
# Import / publish / rollback domain errors
# ---------------------------------------------------------------------------


def test_publish_unknown_version_raises_not_found(store: Database) -> None:
    _create(store)
    with pytest.raises(ResourceNotFound):
        ResourceService().publish_version(
            "doc/a", "no-such", reason="ship it"
        )


def test_rollback_unknown_resource_raises(store: Database) -> None:
    with pytest.raises(ResourceNotFound):
        ResourceService().rollback_resource(
            "missing", target_version=1, reason="rb"
        )


def test_import_upload_version_missing_resource_raises(store: Database) -> None:
    with pytest.raises(ResourceNotFound):
        ResourceService().import_upload_version(
            "missing",
                        filename="x.txt",
            content=b"x",
            mime_type="text/plain",
            changelog="add",
        )


def test_import_zip_rejects_non_folder_or_skill(store: Database) -> None:
    _create(store)  # type='document'
    res = ResourceService().get_resource("doc/a")
    resource_id = res["resource"]["id"]
    with pytest.raises(InvalidResource):
        ResourceService().import_zip_version(
            resource_id,
                        filename="bundle.zip",
            content=b"zip",
            changelog="add",
        )
