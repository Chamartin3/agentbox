"""Live Ollama smoke tests for the token backend (Plan 16 Phase 1.3).

Opt-in only. Skipped unless ``OLLAMA_HOST`` is set in the environment.
Bring up the model server with::

    docker compose --profile verify up -d ollama ollama-seed
    OLLAMA_HOST=http://localhost:11434 uv run pytest -m live_ollama -v

The tests exercise the token backend end-to-end against a real model.
They intentionally use the tiny ``llama3.2:1b`` and
``qwen2.5-coder:0.5b`` models seeded by ``ollama-seed`` so they finish
in seconds.

These tests are a starting scaffold — additional scenarios (streaming
deltas, tool round-trip, structured output, timeout, WS-vs-transcript)
land alongside Phase 1.4's ``scripts/verify_ollama.py`` driver.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from agentbox.core.data import DoneEvent, LogEvent, TextEvent
from agentbox.core.engines.backends.base import RenderedConfig
from agentbox.core.engines.backends.token import TokenBackend

pytestmark = [
    pytest.mark.live_ollama,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        "OLLAMA_HOST" not in os.environ,
        reason="set OLLAMA_HOST to run live Ollama tests",
    ),
]


def _rendered(model: str) -> RenderedConfig:
    return RenderedConfig(
        cwd=Path("."),
        files={},
        agent_meta={
            "agent_module": None,
            "prompt": "You answer in one short sentence.",
            "model": model,
            "output_schema": None,
        },
        model=model,
    )


async def _collect(agen):
    return [ev async for ev in agen]


async def test_ollama_text_only_run() -> None:
    """Scenario 1 — text-only success against a real model."""
    events = await _collect(
        TokenBackend().run(_rendered("ollama:llama3.2:1b"), "Say hello.", "rid")
    )

    types_ = [e.type for e in events]
    assert types_[0] == "log"
    assert isinstance(events[-1], DoneEvent) and events[-1].ok is True
    roles = [e.role for e in events if isinstance(e, TextEvent) and not e.delta]
    assert roles[:2] == ["system", "user"], "system + user turns must be present"
    assert "assistant" in roles, "assistant turn must be present"


async def test_ollama_invalid_model_surfaces_clear_error() -> None:
    """Scenario 4 — provider error keeps prompt turns + surfaces a log."""
    events = await _collect(
        TokenBackend().run(_rendered("ollama:does-not-exist-xyz"), "hi", "rid")
    )
    assert isinstance(events[-1], DoneEvent) and events[-1].ok is False
    roles = [e.role for e in events if isinstance(e, TextEvent) and not e.delta]
    assert roles[:2] == ["system", "user"], (
        "system + user turns must persist even on provider error"
    )
    err_logs = [e for e in events if isinstance(e, LogEvent) and e.level == "error"]
    assert err_logs, "missing-model error must surface a LogEvent(level='error')"
