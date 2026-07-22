"""Credential API — global inventory, add/delete, per-workspace enablement.

Values are never returned by any endpoint; there is no reveal route.
"""

from __future__ import annotations

from typing import Any


def test_inventory_lists_sources_without_values(client: Any) -> None:
    r = client.get("/api/credentials")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["items"])
    for e in body["items"]:
        assert set(e) == {"id", "label", "kind", "source", "env_var", "state"}
        assert "secret" not in e


def test_add_then_delete_managed_credential(client: Any) -> None:
    r = client.post(
        "/api/credentials",
        json={"id": "ui.key", "label": "UI Key", "kind": "api_key",
              "env_var": "UI_KEY", "secret": "sk-ui-4321"},
    )
    assert r.status_code == 201
    row = r.json()
    assert row["last_four"] == "4321"
    assert "secret" not in row and "secret_encrypted" not in row

    # it appears in inventory tagged db
    names = {e["id"]: e for e in client.get("/api/credentials").json()["items"]}
    assert names["ui.key"]["source"] == "db"

    assert client.delete("/api/credentials/ui.key").status_code == 204
    assert client.delete("/api/credentials/ui.key").status_code == 404


def test_add_api_key_without_env_var_is_400(client: Any) -> None:
    r = client.post(
        "/api/credentials",
        json={"id": "bad", "label": "Bad", "kind": "api_key", "secret": "x"},
    )
    assert r.status_code == 400


def test_workspace_enablement_roundtrip(client: Any) -> None:
    client.post(
        "/api/credentials",
        json={"id": "ws.k", "label": "K", "kind": "api_key",
              "env_var": "WS_K", "secret": "sk-ws-0000"},
    )
    r = client.put("/api/workspaces/default/credentials", json={"enabled": ["ws.k"]})
    assert r.status_code == 200
    assert r.json()["enabled"] == ["ws.k"]

    r = client.get("/api/workspaces/default/credentials")
    assert r.json()["enabled"] == ["ws.k"]
    assert any(e["id"] == "ws.k" for e in r.json()["available"])


def test_workspace_enable_unknown_id_is_400(client: Any) -> None:
    r = client.put(
        "/api/workspaces/default/credentials", json={"enabled": ["nope"]}
    )
    assert r.status_code == 400


def test_no_reveal_endpoint_exists(client: Any) -> None:
    # There must be no route that returns a token/credential secret value.
    paths = {r.path for r in client.app.routes if hasattr(r, "path")}
    assert not any("reveal" in p for p in paths)
    assert "/api/api-tokens/{token_id}/reveal" not in paths
