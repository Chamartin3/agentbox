"""Pydantic models for system domain (settings, host env configuration)."""

from typing import Any

from pydantic import BaseModel

from agentbox.core.data.base import Timestamped


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
