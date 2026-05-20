from __future__ import annotations

import logging
from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

_DISCOVERED = False


def discover_tools(force: bool = False) -> None:
    """Import every entry point in the agentbox.agent_tools group.

    Best-effort: a broken entry point is logged and skipped.
    Idempotent — subsequent calls are no-ops unless force=True.
    """
    global _DISCOVERED
    if _DISCOVERED and not force:
        return
    eps = entry_points(group="agentbox.agent_tools")
    for ep in eps:
        try:
            ep.load()
            logger.debug("agent_tools: discovered %r from %r", ep.name, ep.value)
        except Exception:
            logger.exception(
                "agent_tools: failed to load entry point %r (%r) — skipping",
                ep.name,
                ep.value,
            )
    _DISCOVERED = True
