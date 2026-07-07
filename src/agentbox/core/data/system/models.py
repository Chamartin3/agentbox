"""Pydantic models for system domain (API tokens, settings, host env configuration)."""

from typing import Any

from pydantic import BaseModel

from agentbox.core.data.base import Timestamped


class ApiTokenRow(Timestamped):
    """A full row from ``api_tokens`` (includes encrypted secret)."""

    id: str
    environment: str
    name: str
    secret_encrypted: str
    last_four: str
    updated_at: str


class ApiTokenPublicRow(Timestamped):
    """Public view returned by :py:meth:`ApiTokenManager.insert_token` (no secret)."""

    id: str
    environment: str
    name: str
    last_four: str
    updated_at: str


class HostEnvProfileRow(Timestamped):
    """A row from ``host_env_profiles``."""

    id: str
    name: str
    description: str | None = None
    grants: dict[str, Any]
    created_by: str | None = None


class HostEnvCallLogRow(Timestamped):
    """A row from ``host_env_call_log``."""

    id: str
    run_id: str
    workspace_id: str
    capability: str
    params: dict[str, Any] | None = None
    status: str
    error: str | None = None
    surface: str


class SettingKeyRow(BaseModel):
    """A ``{key, value_json}`` pair returned by :py:meth:`SettingManager.get_section`."""

    key: str
    value_json: str
