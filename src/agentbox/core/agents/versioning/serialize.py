"""Agent-version serializers.

These two functions produce the JSON strings stored in
``agent_versions.content_snapshot`` and ``agent_versions.config_json``.
They live here — not in the now-deleted drift module — because they are
pure AgentDef → str serializers used by every version-write path, not
part of the drift-import subsystem.
"""

from __future__ import annotations

import json
import warnings

from agentbox.core.agents.definition import build_config_json_payload
from agentbox.core.data import AgentDef


def build_agent_snapshot(agent: AgentDef) -> str:
    """Serialize an ``AgentDef`` for the ``content_snapshot`` column."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        data = agent.model_dump(mode="python")
    return json.dumps(data, sort_keys=True, default=str)


def build_config_json_str(agent: AgentDef) -> str:
    """Serialize an ``AgentDef`` for the ``agent_versions.config_json`` column.

    Distinct from ``build_agent_snapshot`` (which targets ``content_snapshot``):
    ``config_json`` is the DB-as-source-of-truth payload consumed by
    ``AgentDef.from_db_row`` at runtime, so it MUST round-trip every
    runner field — defaults included — to prevent silent revert to the
    pydantic default at read time.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        data = agent.model_dump(mode="json", exclude_none=False)
    # Merge in structured execution/runtime/python sub-dicts so the config
    # snapshot is self-contained and needs no runner-fallback at read time.
    data.update(build_config_json_payload(agent))
    return json.dumps(data, sort_keys=True, default=str)
