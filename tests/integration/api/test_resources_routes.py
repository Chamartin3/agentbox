"""HTTP API tests for shared resources CRUD + versioning endpoints."""

from __future__ import annotations


def test_create_and_get_active_resource(client) -> None:  # type: ignore[no-untyped-def]
    """POST resource, then GET /{id} returns the active version."""
    # Create a resource
    create_resp = client.post(
        "/api/resources",
        json={
            "id": "test-resource",
            "kind": "output_schema",
            "name": "Test Schema",
            "description": "A test schema",
            "content": "{}",
            "author": "test_author",
            "changelog": "Initial version",
            "tags": ["test"],
            "activate": True,
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["id"] == "test-resource"
    assert data["kind"] == "output_schema"
    assert data["version"] == 1
    assert data["is_active"] is True

    # Get the active resource
    get_resp = client.get("/api/resources/test-resource")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == "test-resource"
    assert data["version"] == 1
    assert data["is_active"] is True


def test_create_duplicate_returns_409(client) -> None:  # type: ignore[no-untyped-def]
    """Creating a resource with duplicate id returns 409."""
    # Create first resource
    client.post(
        "/api/resources",
        json={
            "id": "duplicate-test",
            "kind": "input_schema",
            "name": "First",
            "author": "author1",
            "changelog": "First version",
        },
    )

    # Try to create another with same id
    dup_resp = client.post(
        "/api/resources",
        json={
            "id": "duplicate-test",
            "kind": "system_fragment",
            "name": "Second",
            "author": "author2",
            "changelog": "Second version",
        },
    )
    assert dup_resp.status_code == 409


def test_list_resources_filters_by_kind(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/resources?kind=X filters by resource kind."""
    # Create resources of different kinds
    client.post(
        "/api/resources",
        json={
            "id": "schema1",
            "kind": "output_schema",
            "name": "Output Schema 1",
            "author": "author",
            "changelog": "Version 1",
        },
    )
    client.post(
        "/api/resources",
        json={
            "id": "template1",
            "kind": "user_template",
            "name": "Template 1",
            "author": "author",
            "changelog": "Version 1",
        },
    )

    # List only output_schema
    resp = client.get("/api/resources?kind=output_schema")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "output_schema"
    assert items[0]["id"] == "schema1"


def test_list_resources_filters_by_query(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/resources?q=X filters by name/description search."""
    # Create resources with distinct names and descriptions
    client.post(
        "/api/resources",
        json={
            "id": "res1",
            "kind": "reference",
            "name": "Important Document",
            "description": "Contains critical data",
            "author": "author",
            "changelog": "Initial",
        },
    )
    client.post(
        "/api/resources",
        json={
            "id": "res2",
            "kind": "reference",
            "name": "Other Resource",
            "description": "Less important",
            "author": "author",
            "changelog": "Initial",
        },
    )

    # Search for "critical"
    resp = client.get("/api/resources?q=critical")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == "res1"


def test_list_resource_versions_single(client) -> None:  # type: ignore[no-untyped-def]
    """GET /versions on a single-version resource returns that version."""
    # Create a resource
    client.post(
        "/api/resources",
        json={
            "id": "single-ver",
            "kind": "skill",
            "name": "Single Version",
            "content": "v1 content",
            "author": "author1",
            "changelog": "Initial release",
            "activate": True,
        },
    )

    # List versions - should have only one
    list_resp = client.get("/api/resources/single-ver/versions")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["version"] == 1
    assert items[0]["is_active"] is True


def test_activate_version_on_nonexistent_returns_404(client) -> None:  # type: ignore[no-untyped-def]
    """POST activate on non-existent version returns 404."""
    # Try to activate a non-existent version
    resp = client.post(
        "/api/resources/nonexistent/activate",
        json={"version": 5},
    )
    assert resp.status_code == 404


def test_get_missing_resource_returns_404(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/resources/{id} returns 404 for non-existent resource."""
    resp = client.get("/api/resources/nonexistent")
    assert resp.status_code == 404


def test_create_resource_missing_author_returns_422(client) -> None:  # type: ignore[no-untyped-def]
    """POST without author returns 422 (Pydantic validation)."""
    resp = client.post(
        "/api/resources",
        json={
            "id": "test",
            "kind": "output_schema",
            "name": "Test",
            "changelog": "Initial",
            # author is missing
        },
    )
    assert resp.status_code == 422


def test_create_resource_short_changelog_returns_400(client) -> None:  # type: ignore[no-untyped-def]
    """POST with changelog < 3 chars returns 400."""
    resp = client.post(
        "/api/resources",
        json={
            "id": "test",
            "kind": "output_schema",
            "name": "Test",
            "author": "author",
            "changelog": "ab",  # Too short (< 3 chars)
        },
    )
    assert resp.status_code == 400, (
        f"Expected 400, got {resp.status_code}: {resp.json()}"
    )


def test_create_version_missing_resource_returns_404(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/resources/{id}/versions on non-existent id returns 404."""
    resp = client.post(
        "/api/resources/nonexistent/versions",
        json={
            "content": "new content",
            "author": "author",
            "changelog": "New version",
        },
    )
    assert resp.status_code == 404


def test_activate_missing_version_returns_404(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/resources/{id}/activate with non-existent version returns 404."""
    # Create a resource
    client.post(
        "/api/resources",
        json={
            "id": "test",
            "kind": "output_schema",
            "name": "Test",
            "author": "author",
            "changelog": "Initial",
        },
    )

    # Try to activate non-existent version
    resp = client.post(
        "/api/resources/test/activate",
        json={"version": 99},
    )
    assert resp.status_code == 404


def test_resource_tags_serialization(client) -> None:  # type: ignore[no-untyped-def]
    """Tags are stored and returned as a list in JSON."""
    # Create with tags
    create_resp = client.post(
        "/api/resources",
        json={
            "id": "tagged-res",
            "kind": "reference",
            "name": "Tagged Resource",
            "tags": ["tag1", "tag2", "tag3"],
            "author": "author",
            "changelog": "With tags",
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["tags"] == ["tag1", "tag2", "tag3"]

    # Get and verify tags
    get_resp = client.get("/api/resources/tagged-res")
    assert get_resp.json()["tags"] == ["tag1", "tag2", "tag3"]
