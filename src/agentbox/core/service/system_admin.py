"""System administration service — settings, API tokens, and project MCP config.

Pass-through functions over ``SessionStore``. UI layers call these instead
of reaching into ``SessionStore`` directly.
"""

from __future__ import annotations

import secrets as _secrets

from agentbox.core.db import McpServerSpec
from agentbox.core.db import SessionStore


# ── Settings ────────────────────────────────────────────────────────────


def get_settings_section(store: SessionStore, section: str) -> dict:
    return store.get_settings_section(section)


def list_settings_sections(store: SessionStore) -> list[str]:
    return store.list_settings_sections()


def update_settings_section(
    store: SessionStore,
    section: str,
    patch: dict,
    *,
    author: str | None = None,
) -> dict:
    return store.update_settings_section(section, patch, author=author)


def set_setting(
    store: SessionStore,
    section: str,
    key: str,
    value: object,
    *,
    author: str | None = None,
) -> None:
    store.set_setting(section, key, value, author=author)


# ── API tokens ──────────────────────────────────────────────────────────


def list_api_tokens(
    store: SessionStore, *, environment: str | None = None
) -> list[dict]:
    return store.list_api_tokens(environment=environment)


def create_api_token(
    store: SessionStore,
    name: str,
    *,
    environment: str = "production",
) -> dict:
    secret = _secrets.token_urlsafe(32)
    return store.create_api_token(environment=environment, name=name, secret=secret)


def rotate_api_token(
    store: SessionStore,
    token_id: str,
    *,
    secret: str | None = None,
) -> dict | None:
    if secret is None:
        secret = _secrets.token_urlsafe(32)
    return store.rotate_api_token(token_id, secret=secret)


def delete_api_token(store: SessionStore, token_id: str) -> bool:
    return store.delete_api_token(token_id)


# ── Project MCP servers ─────────────────────────────────────────────────


def get_project_mcp_servers(store: SessionStore) -> list[McpServerSpec]:
    return store.get_project_mcp_servers()


def set_project_mcp_server(
    store: SessionStore,
    spec: McpServerSpec,
    *,
    author: str | None = None,
) -> None:
    store.set_project_mcp_server(spec, author=author)


def delete_project_mcp_server(store: SessionStore, name: str) -> None:
    store.delete_project_mcp_server(name)


# ── Project shared assets ───────────────────────────────────────────────


def set_project_shared_asset(
    store: SessionStore,
    name: str,
    path: str,
    *,
    author: str | None = None,
) -> None:
    store.set_project_shared_asset(name, path, author=author)
