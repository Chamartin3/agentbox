"""Config generator helpers extracted from RunSetup.

This module retains only the agent-config reader used exclusively by
:class:`~.setup.RunSetup`.
"""

from __future__ import annotations

import json as _json
from typing import Any


def _read_agent_config_json(agent: Any) -> dict[str, Any]:
    """Read the ``config_json`` dict attached to an agent, if any.

    ``config_json`` lives on ``agent_versions`` and is attached to the
    agent object via ``agent.__dict__["_config_json"]`` during DB load.
    Returns the full parsed dict or an empty dict.
    """
    raw = agent.__dict__.get("_config_json") if hasattr(agent, "__dict__") else None
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}
