"""Conversation source for OpenCode session exports.

Reads a conversation from ``opencode export <session_id>``. The export
includes full message history (user, assistant with thinking/tool_use
parts), model info, and token usage.

Runtime requirement: the ``opencode`` CLI must be installed on PATH in
the process hosting the MCP server / API. When it isn't, ``load()``
returns an empty ``ConversationView`` with ``source_uri`` set to the
session id so the caller can render a clear "CLI unavailable" hint.
A future refactor may read the session JSON directly from
``~/.local/share/opencode/storage/`` to drop this dependency.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from contextlib import suppress
from typing import TYPE_CHECKING

from agentbox.core.run.history.base import ConversationSource
from agentbox.core.run.history.types import (
    ContentPart,
    ConversationView,
    TokenTotals,
    Turn,
)

if TYPE_CHECKING:
    from agentbox.core.data import RunRecord


class OpencodeSessionSource(ConversationSource):
    """Parse an OpenCode session export into a ``ConversationView``.

    The session is loaded by running ``opencode export <session_id>``,
    which returns JSON with ``info`` (model, tokens) and ``messages``
    (conversation turns with typing/text/tool_use parts).
    """

    format = "opencode-session"

    def __init__(
        self,
        session_id: str | None = None,
        workdir: str | None = None,
    ) -> None:
        self._session_id = session_id
        self._workdir = workdir

    @classmethod
    def for_run(cls, run: RunRecord) -> ConversationSource | None:
        sid = getattr(run, "conversation_uri", None)
        if not sid:
            return None
        wd = getattr(run, "workdir", None)
        return cls(session_id=sid, workdir=wd)

    def _export_session(self) -> dict | None:
        """Run ``opencode export <session_id>`` and return parsed JSON.

        Synchronous: this source is called from FastMCP / FastAPI handlers
        that may already be inside an event loop, so we can't use
        ``asyncio.run`` here. Plain ``subprocess`` with a timeout is fine
        because the export is bounded and short.

        Requires the ``opencode`` CLI to be available on PATH in the
        process hosting the MCP server / API.
        """
        if not self._session_id:
            return None
        if shutil.which("opencode") is None:
            return None
        try:
            proc = subprocess.run(
                ["opencode", "export", self._session_id],
                capture_output=True,
                timeout=15,
                cwd=self._workdir or None,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if proc.returncode != 0:
            return None
        raw = proc.stdout.decode(errors="replace")
        start = raw.find("{")
        if start < 0:
            return None
        try:
            return json.loads(raw[start:])
        except json.JSONDecodeError:
            return None

    def load(
        self,
        *,
        include_bodies: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> ConversationView:
        run_id = "?"
        data = self._export_session()
        if data is None:
            return ConversationView(
                run_id=run_id,
                session_id=self._session_id,
                source_format=self.format,
                source_uri=self._session_id,
                totals=TokenTotals(),
            )

        info = data.get("info") if isinstance(data, dict) else None
        messages = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(messages, list):
            messages = []

        totals = TokenTotals()
        if isinstance(info, dict):
            tokens_raw = info.get("tokens")
            tokens = tokens_raw if isinstance(tokens_raw, dict) else {}
            cache_raw = tokens.get("cache")
            cache = cache_raw if isinstance(cache_raw, dict) else {}
            totals.input_tokens = int(tokens.get("input") or 0)
            totals.output_tokens = int(tokens.get("output") or 0)
            totals.cache_read_tokens = int(cache.get("read") or 0)
            totals.cache_write_tokens = int(cache.get("write") or 0)
            cost = info.get("cost")
            with suppress(TypeError, ValueError):
                totals.cost_usd = float(cost) if cost is not None else None

        turns: list[Turn] = []
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "user")
            parts: list[ContentPart] = []
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(
                    ContentPart(
                        type="text",
                        byte_len=len(content),
                        body=content if include_bodies else None,
                    )
                )
            elif isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    ct = c.get("type", "")
                    if ct == "text":
                        body = c.get("text", "") or ""
                        parts.append(
                            ContentPart(
                                type="text",
                                byte_len=len(body),
                                body=body if include_bodies else None,
                            )
                        )
                    elif ct == "thinking":
                        body = c.get("thinking", "") or ""
                        parts.append(
                            ContentPart(
                                type="thinking",
                                byte_len=len(body),
                                body=body if include_bodies else None,
                            )
                        )
                    elif ct == "tool_use":
                        ti = c.get("input")
                        tool_name = c.get("name")
                        body_str = json.dumps(ti) if ti is not None else None
                        parts.append(
                            ContentPart(
                                type="tool_use",
                                byte_len=len(body_str) if body_str else 0,
                                body=body_str if include_bodies else None,
                                tool_name=tool_name,
                                tool_use_id=c.get("id") or c.get("tool_use_id"),
                            )
                        )
                    elif ct == "tool_result":
                        content_body = c.get("content")
                        body_str = (
                            json.dumps(content_body)
                            if not isinstance(content_body, str)
                            else content_body
                        )
                        parts.append(
                            ContentPart(
                                type="tool_result",
                                byte_len=len(body_str) if body_str else 0,
                                body=body_str if include_bodies else None,
                                tool_use_id=c.get("tool_use_id"),
                            )
                        )
            turns.append(Turn(index=i, role=role, content=parts))  # type: ignore[arg-type]

        page = turns[offset : offset + limit]
        return ConversationView(
            run_id=run_id,
            session_id=self._session_id,
            source_format=self.format,
            source_uri=self._session_id,
            totals=totals,
            turns=page,
        )
