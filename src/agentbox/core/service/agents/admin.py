"""Agent administration service — version config replacement and meta updates.

Extracted from ``core.service.workspace_admin`` to separate agent concerns
from workspace concerns per the domain split.
"""

from __future__ import annotations

from agentbox.core.data import SessionStore


def replace_version_config(
    store: SessionStore, version_id: int, config_json: str
) -> None:
    """Replace the config_json payload on an agent version."""
    store.replace_version_config(version_id, config_json)


def update_agent_meta(
    store: SessionStore,
    agent_id: str,
    *,
    sync_mode: str | None = None,
    export_to_disk: bool | None = None,
    source_path: str | None = None,
    source_format: str | None = None,
) -> dict | None:
    """Update agent metadata fields."""
    return store.update_agent_meta(
        agent_id,
        sync_mode=sync_mode,
        export_to_disk=export_to_disk,
        source_path=source_path,
        source_format=source_format,
    )
