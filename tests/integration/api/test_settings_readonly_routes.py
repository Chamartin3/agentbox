"""Read-only settings surfaces: deployment view + env-secret names."""

from __future__ import annotations

from typing import Any


def test_deployment_view_lists_env_config_without_leaking_secrets(client: Any) -> None:
    r = client.get("/api/settings/deployment")
    assert r.status_code == 200
    groups = r.json()["groups"]
    # Grouped, and the well-known knobs are present.
    assert {"Paths", "Server", "MCP", "Environment"} <= set(groups)
    names = {e["name"] for g in groups.values() for e in g}
    assert {"data_dir", "host", "port", "mcp_transport"} <= names
    # Secrets are masked to set/unset — never the raw value.
    server = {e["name"]: e["value"] for e in groups["Server"]}
    assert server["webhook_secret"] in {"set", "unset"}
    assert server["secret_key"] in {"set", "unset"}


def test_env_secrets_returns_names_only(client: Any, monkeypatch: Any, tmp_path: Any) -> None:
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / ".env").write_text("OPENROUTER_API_KEY=sk-secret\nOLLAMA_HOST=http://x\n")
    monkeypatch.setenv("AGENTBOX_CREDS_DIR", str(creds))

    r = client.get("/api/settings/env-secrets")
    assert r.status_code == 200
    body = r.json()
    assert body["names"] == ["OLLAMA_HOST", "OPENROUTER_API_KEY"]  # sorted, names only
    assert "sk-secret" not in r.text  # value never returned
