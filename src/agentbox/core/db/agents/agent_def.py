"""AgentDefManager — purpose-specific multi-table read.

Reconstructs an ``AgentDef`` from the active (else latest) agent version plus
a soft-delete check on ``agent_meta``. This is a read-only projection of rows
into a ``core.data`` shape — no business logic (that stays in Services).

It exists so callers that need an ``AgentDef`` never reach for the ``Database``
object or compose two managers by hand: it IS the purpose-specific manager for
this cross-table read (relocated off ``Database.get_agent_def``).
"""
from __future__ import annotations

from typing import Any

from agentbox.core.data import AgentDef
from agentbox.core.db.agents.agent import AgentMetaManager
from agentbox.core.db.agents.version import AgentVersionManager


class AgentDefManager:
	"""Composite reader: active-else-latest version + soft-delete → ``AgentDef``."""

	def __init__(self, engine: Any) -> None:
		self._versions = AgentVersionManager(engine)
		self._meta = AgentMetaManager(engine)

	def get(self, agent_id: str) -> AgentDef | None:
		"""Return the ``AgentDef`` for *agent_id*, or ``None``.

		``None`` when the agent has never been versioned, is soft-deleted, or
		the stored snapshot fails validation. Mirrors ``AgentService.get_agent_def``.
		"""
		row = self._versions.get_effective_active(agent_id)
		if row is None:
			return None
		meta = self._meta.get_meta(agent_id)
		if meta and meta.get("deleted_at"):
			return None
		try:
			return AgentDef.from_db_row(row)
		except Exception:
			return None
