"""Conversation source for Claude CLI's native session log format.

Reads ``CLAUDE_CONFIG_DIR`` directly from the environment (not from
``Settings``). This is the one source that had its config path smuggled
through the global settings dataclass — the whole point of this module is
to keep storage-layout knowledge inside the source.
"""

from __future__ import annotations

import os
from pathlib import Path

from agentbox.core.data import RunRecord
from agentbox.core.data.conversation.base import ConversationSource
from agentbox.core.data.conversation.types import ConversationView, TokenTotals
from agentbox.core.engines.backends.claude_code.session_log import (
    find_session_log,
    parse_session_log,
)


class ClaudeCliJsonlSource(ConversationSource):
    """Parses the Claude CLI JSONL session log for a given run.

    The Claude CLI persists a per-session JSONL log under
    ``$CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/<session-uuid>.jsonl``.
    Each line is a typed entry (``user``, ``assistant``, ``system``, …)
    that captures the full conversation including ``thinking`` blocks,
    ``tool_use`` calls, ``stop_reason``, and per-turn ``usage``.
    """

    format = "claude-cli-jsonl"

    def __init__(self, transcript_path: Path | None = None) -> None:
        self._transcript_path = transcript_path

    @classmethod
    def for_run(cls, run: RunRecord) -> ConversationSource | None:
        tp = Path(run.transcript_path) if run and run.transcript_path else None
        return cls(transcript_path=tp)

    def _claude_projects_root(self) -> Path | None:
        """Return the Claude CLI projects root from env, or None."""
        config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
        if not config_dir:
            return None
        return Path(config_dir) / "projects"

    def load(
        self,
        *,
        include_bodies: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> ConversationView:
        run_id = "?"
        tp = self._transcript_path
        projects = self._claude_projects_root()

        if tp is None or not tp.exists() or projects is None:
            return ConversationView(
                run_id=run_id,
                session_id=None,
                source_format=self.format,
                source_uri=str(tp) if tp else None,
                totals=TokenTotals(),
            )

        log_path = find_session_log(tp, projects)
        if log_path is None:
            return ConversationView(
                run_id=run_id,
                session_id=None,
                source_format=self.format,
                source_uri=str(tp),
                totals=TokenTotals(),
            )

        # The parser already emits the runner-agnostic ConversationView;
        # fill in run identity and page the turns.
        view = parse_session_log(log_path, include_bodies=include_bodies)
        view.run_id = run_id
        view.turns = view.turns[offset : offset + limit]
        return view
