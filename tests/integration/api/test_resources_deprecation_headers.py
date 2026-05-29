"""Legacy /api/resources surface must advertise RFC 8594 Deprecation."""

from __future__ import annotations

from typing import Any


def test_list_resources_emits_deprecation_headers(client: Any) -> None:
    resp = client.get("/api/resources")
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    link = resp.headers.get("Link", "")
    assert "/api/repo-resources" in link
    assert 'rel="successor-version"' in link


def test_list_resource_versions_emits_deprecation_headers(client: Any) -> None:
    # Another endpoint on the same router — confirms the dependency is
    # applied router-wide rather than per-route.
    resp = client.get("/api/resources/missing/versions")
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "/api/repo-resources" in resp.headers.get("Link", "")
