"""Agent administration service — version config replacement and meta updates.

Extracted from ``core.service.workspace_admin`` to separate agent concerns
from workspace concerns per the domain split.
"""

from __future__ import annotations

from agentbox.core.data import AgentMetaRow
from agentbox.core.data._util import now_iso
from agentbox.core.db import AgentMetaManager, AgentVersionManager


def replace_version_config(
    agent_versions: AgentVersionManager, version_id: int, config_json: str
) -> None:
    """Replace the config_json payload on an agent version."""
    agent_versions.patch(version_id, config_json=config_json)


def update_agent_meta(
    agent_meta: AgentMetaManager,
    agent_id: str,
    *,
    sync_mode: str | None = None,
    export_to_disk: bool | None = None,
    source_path: str | None = None,
    source_format: str | None = None,
) -> AgentMetaRow | None:
    """Update agent metadata fields."""
    if agent_meta.get_meta(agent_id) is None:
        return None
    values: dict = {"updated_at": now_iso()}
    if sync_mode is not None:
        values["sync_mode"] = sync_mode
    if export_to_disk is not None:
        values["export_to_disk"] = int(export_to_disk)
    if source_path is not None:
        values["source_path"] = source_path
    if source_format is not None:
        values["source_format"] = source_format
    agent_meta.patch(agent_id, **values)
    return agent_meta.get_meta(agent_id)
