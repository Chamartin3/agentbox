"""Shared agent-resolution service used by both REST and MCP surfaces.

The DB (``agent_versions`` / ``active_agent_versions``) is the single
source of truth. There is no manifest fallback — the deprecated disk
loader does not participate in agent resolution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentbox.core.data.manifest import AgentDef
    from agentbox.core.data.store import SessionStore

logger = logging.getLogger(__name__)


def resolve_agent(
    agent_id: str,
    *,
    store: SessionStore,
    loader: Any = None,
) -> AgentDef | None:
    """Return the ``AgentDef`` for ``agent_id`` from the DB, or ``None``.

    ``loader`` is accepted for backward compatibility with call sites that
    still thread it; it is ignored. Disk-only agents must be imported into
    the DB before they can be resolved.
    """
    del loader  # deprecated, ignored
    return store.get_agent_def(agent_id)


def list_all_agents(
    *,
    store: SessionStore,
    loader: Any = None,
) -> list[AgentDef]:
    """Return every known agent from the DB (latest snapshot per id).

    Snapshot rows that fail validation are skipped with a warning so a
    single bad row never blanks the whole list. ``loader`` is accepted
    for backward compatibility and ignored.
    """
    del loader  # deprecated, ignored
    from agentbox.core.data.manifest import AgentDef

    out: list[AgentDef] = []
    for row in store.list_agents_with_latest():
        try:
            agent = AgentDef.from_db_row(row)
        except ValueError:
            continue
        except Exception:
            logger.exception(
                "list_all_agents: snapshot for %r v%s failed validation",
                row.get("agent_id"),
                row.get("version"),
            )
            continue
        out.append(agent)
    return out
