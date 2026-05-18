"""Conversation source for PydanticAI runs.

PydanticAI runs in-process and doesn't persist a native session log.
All available conversation data comes from the agentbox JSONL transcript
(TextEvent, UsageEvent, DoneEvent events).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.data.transcripts import read_transcript
from agentbox.core.run.history.base import ConversationSource
from agentbox.core.run.history.sources.transcript import (
    _events_to_conversation_view,
)
from agentbox.core.run.history.types import ConversationView, TokenTotals

if TYPE_CHECKING:
    from agentbox.core.data.records import RunRecord


class PydanticAiHistorySource(ConversationSource):
    """Reconstruct a conversation view for PydanticAI runs from the
    agentbox transcript.
    """

    format = "pydantic-ai-history"

    def __init__(self, transcript_path: Path | None = None) -> None:
        self._transcript_path = transcript_path

    @classmethod
    def for_run(cls, run: RunRecord) -> ConversationSource | None:
        tp = Path(run.transcript_path) if run.transcript_path else None
        return cls(transcript_path=tp)

    def load(
        self,
        *,
        include_bodies: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> ConversationView:
        tp = self._transcript_path
        if tp is None or not tp.exists():
            return ConversationView(
                run_id="?",
                session_id=None,
                source_format=self.format,
                source_uri=str(tp) if tp else None,
                totals=TokenTotals(),
            )

        events = read_transcript(tp)
        return _events_to_conversation_view(
            events=events,
            run_id="?",
            source_format=self.format,
            source_uri=str(tp),
            include_bodies=include_bodies,
            offset=offset,
            limit=limit,
        )
