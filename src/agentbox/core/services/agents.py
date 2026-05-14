"""Shared agent-resolution service used by both REST and MCP surfaces.

The DB (``agent_versions`` / ``active_agent_versions``) is the source of
truth — the manifest loader is consulted only as a fallback for agents
that exist on disk but have not yet been imported into the DB. Keeping
this logic in one place is what guarantees REST ``/api/agents`` and the
MCP ``get_agent`` / ``list_agents`` tools agree.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data.manifest import AgentDef
    from agentbox.core.data.store import SessionStore
    from agentbox.core.definitions.loader import DefinitionLoader

logger = logging.getLogger(__name__)


def resolve_agent(
    agent_id: str,
    *,
    store: SessionStore,
    loader: DefinitionLoader,
) -> AgentDef | None:
    """Return the ``AgentDef`` for ``agent_id`` — DB first, manifest fallback.

    Mirrors ``api/routes/agents.py:get_agent``. Use this everywhere an
    agent must be looked up so REST and MCP agree on existence.
    """
    return store.get_agent_def(agent_id) or loader.get(agent_id)


def list_all_agents(
    *,
    store: SessionStore,
    loader: DefinitionLoader,
) -> list[AgentDef]:
    """Return every known agent — DB rows first, manifest-only as fallback.

    Mirrors the union performed by ``api/routes/agents.py:list_agents``.
    Order: DB agents (latest snapshot per id), then any manifest agents
    not present in the DB. Snapshot rows that fail validation are skipped
    with a warning so a single bad row never blanks the whole list.
    """
    from agentbox.core.data.manifest import AgentDef

    seen: set[str] = set()
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
        seen.add(agent.id)

    try:
        manifest = loader.load()
    except Exception:
        logger.exception("list_all_agents: manifest load failed")
        manifest = None

    if manifest is not None:
        for agent in manifest.agents:
            if agent.id in seen:
                continue
            out.append(agent)
            seen.add(agent.id)

    return out
