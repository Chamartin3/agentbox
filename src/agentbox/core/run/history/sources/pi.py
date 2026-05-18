"""Conversation source for pi sessions.

Plan 16 Phase 2 — first cut. pi exposes session state on disk under
``~/.pi/sessions/`` but the schema isn't pinned across versions; rather
than guess, this source returns an empty ``ConversationView`` pointing
at the captured session id so the UI / MCP can fall back to the
agentbox JSONL transcript.

Promote to a real parser once the pi session layout is stable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.run.history.base import ConversationSource
from agentbox.core.run.history.types import ConversationView, TokenTotals

if TYPE_CHECKING:
    from agentbox.core.data.records import RunRecord


class PiSessionSource(ConversationSource):
    format = "pi-session"

    def __init__(self, session_id: str | None = None) -> None:
        self._session_id = session_id

    @classmethod
    def for_run(cls, run: RunRecord) -> ConversationSource | None:
        sid = getattr(run, "conversation_uri", None)
        if not sid:
            return None
        return cls(session_id=sid)

    def load(
        self,
        *,
        include_bodies: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> ConversationView:
        return ConversationView(
            run_id="?",
            session_id=self._session_id,
            source_format=self.format,
            source_uri=self._session_id,
            totals=TokenTotals(),
        )
