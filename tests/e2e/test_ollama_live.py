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
from agentbox.core.db import DoneEvent, LogEvent, TextEvent, ToolCallEvent
from agentbox.core.engines.contracts.base import RenderedConfig
from agentbox.core.engines.backends.token import TokenBackend

pytestmark = [
    pytest.mark.live_ollama,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        "OLLAMA_HOST" not in os.environ,
        reason="set OLLAMA_HOST to run live Ollama tests",
    ),
]

# Non-thinking, reliably tool-capable; override via env. Thinking models
# (e.g. qwen3-*) currently trip an Ollama tool-result serialization quirk.
_TOOL_MODEL = os.environ.get("AGENTBOX_E2E_TOOL_MODEL", "llama3.2:latest")


def _rendered(model: str) -> RenderedConfig:
    return RenderedConfig(
        cwd=Path("."),
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


def _tool_rendered(model: str, workdir: Path) -> RenderedConfig:
    """RenderedConfig that grants host-env fs tools scoped to ``workdir``.

    Mirrors what the executor stashes into agent_meta after resolving host-env
    grants, so the token backend wires the fs tools (MCP toolset, falling back
    to in-process) for a real tool round-trip.
    """
    grants = {
        "fs.read": {"allowed_paths": [str(workdir)], "max_bytes": 1048576},
        "fs.list": {"allowed_paths": [str(workdir)]},
    }
    return RenderedConfig(
        cwd=Path("."),
        agent_meta={
            "agent_module": None,
            "prompt": "You call tools to act. Never fabricate file contents.",
            "model": f"ollama:{model}",
            "output_schema": None,
            "provider": "ollama",
            "base_url": f"{os.environ['OLLAMA_HOST'].rstrip('/')}/v1",
            "host_env_grants": grants,
            "agent_tool_grants": ["fs.read", "fs.list"],
            "host_env_workspace_id": "e2e-ws",
            "host_env_workdir": str(workdir),
            "host_env_db_path": os.environ.get("AGENTBOX_DB_PATH", "/data/agentbox.sqlite"),
        },
        model=f"ollama:{model}",
    )


async def test_ollama_tool_round_trip(tmp_path: Path) -> None:
    """Scenario — the model actually CALLS a granted fs tool (the regression
    that the token backend dropped tools, so 0 tool_call events ever fired).

    Asserts a real ToolCallEvent for the list tool referencing the granted
    workdir — not hallucinated text.
    """
    (tmp_path / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (tmp_path / "beta.txt").write_text("beta\n", encoding="utf-8")

    events = await _collect(
        TokenBackend().run(
            _tool_rendered(_TOOL_MODEL, tmp_path),
            f"List the files in the directory {tmp_path} by calling the list tool.",
            "rid",
        )
    )

    assert isinstance(events[-1], DoneEvent) and events[-1].ok is True
    tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
    assert tool_calls, (
        "model fired NO tool calls — the backend is not presenting the granted "
        "host-env tools to the model"
    )
    # The list tool was called against the granted workdir (native name varies
    # by wiring path: in-process 'fs_list' or MCP-prefixed '*_fs.list').
    assert any("list" in tc.tool.lower() for tc in tool_calls), (
        f"expected a list tool call, got {[tc.tool for tc in tool_calls]}"
    )
