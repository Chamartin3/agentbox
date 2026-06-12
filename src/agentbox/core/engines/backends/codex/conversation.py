"""Conversation source for Codex sessions.

Plan 16 Phase 2 — first cut. Codex does not currently expose a stable
``export`` command for replaying past sessions, so this source returns
an empty ``ConversationView`` pointing at the captured session id. The
caller (UI / MCP) can render a "no native conversation available, see
the agentbox transcript" hint and fall back to ``TranscriptSource``.

Once codex exposes a deterministic session export (or a documented
on-disk layout under ``~/.codex/sessions/``), grow this source to parse
the messages into ``Turn`` objects analogous to
:class:`~agentbox.core.engines.backends.opencode.conversation.OpencodeSessionSource`.
"""

from __future__ import annotations

from agentbox.core.data import RunRecord
from agentbox.core.execution.observability.conversation.base import ConversationSource
from agentbox.core.execution.observability.conversation.types import ConversationView, TokenTotals


class CodexSessionSource(ConversationSource):
    format = "codex-session"

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
