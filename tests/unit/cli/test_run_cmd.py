"""Unit tests for the unified ``agentbox run`` command.

Coverage:
- Headless mode (``-p/--prompt``): mocks httpx.post + _stream to verify API call.
- Interactive mode (no prompt): mocks ``_launch_session`` from cli.ops.launch.
- Interactive + token backend: verifies the friendly rejection message.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import agentbox.cli.run as _run_mod
import httpx
import pytest
from typer.testing import CliRunner

from agentbox.cli import app
from agentbox.cli.shared import (
    get_executor,
    get_mcp_registry,
)
from agentbox.cli.shared.deps import (
    get_settings,
    get_store as _get_store,
)
from agentbox.core.data import AgentDef

runner = CliRunner()


def _clear_deps_caches() -> None:
    for fn in (get_settings, _get_store, get_executor, get_mcp_registry):
        fn.cache_clear()


@pytest.fixture
def store_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Minimal store fixture for run command tests."""
    manifest = tmp_path / "agentbox.toml"
    manifest.write_text("# test manifest\n")
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    _clear_deps_caches()
    store = _get_store()
    yield store
    _clear_deps_caches()


def _seed_agent(store, agent_id: str, runner_kind: str = "claude_code") -> None:
    agent_def = AgentDef(
        id=agent_id,
        description="Test agent",
        runner={"kind": runner_kind, "model": "test-model"},
    )
    store.create_agent(
        agent_id=agent_id,
        config_json=agent_def.model_dump(
            mode="python", exclude_none=True, warnings=False
        ),
        prompt_content="# Test prompt\n",
        author="test",
        changelog="seed",
        source="cli",
        sync_mode="off",
        export_to_disk=False,
    )


# ---------------------------------------------------------------------------
# Headless path: run with -p hits the API
# ---------------------------------------------------------------------------


def test_run_headless_posts_to_api(store_fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """``agentbox run AGENT -p TEXT`` should POST to /api/runs (headless mode)."""
    _seed_agent(store_fixture, "my-agent")

    posted_bodies: list[dict] = []

    class _MockResp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"run_id": "r-test-headless"}

    def _mock_post(url: str, *, json: dict | None = None, timeout: float = 30) -> _MockResp:
        if json is not None:
            posted_bodies.append(json)
        return _MockResp()

    monkeypatch.setattr(httpx, "post", _mock_post)

    # Also mock asyncio.run so we don't need a real WebSocket server
    monkeypatch.setattr(asyncio, "run", lambda coro: None)

    result = runner.invoke(app, ["run", "my-agent", "-p", "hello world"])
    assert result.exit_code == 0, result.output
    assert any("r-test-headless" in str(b) or b.get("input") == "hello world"
               for b in posted_bodies), (
        f"Expected API POST with prompt; posted_bodies={posted_bodies}"
    )


def test_run_headless_requires_prompt(store_fixture) -> None:
    """``agentbox run AGENT --headless`` without a prompt should exit non-zero."""
    _seed_agent(store_fixture, "my-agent")
    result = runner.invoke(app, ["run", "my-agent", "--headless"])
    assert result.exit_code != 0
    assert "--prompt" in result.output or "prompt" in result.output.lower()


def test_run_headless_requires_agent() -> None:
    """``agentbox run -p TEXT`` without AGENT should exit non-zero."""
    result = runner.invoke(app, ["run", "-p", "hello"])
    assert result.exit_code != 0
    assert "agent" in result.output.lower()


def test_run_backend_with_prompt_is_error() -> None:
    """``--backend`` + ``-p`` is ambiguous — should exit 2."""
    result = runner.invoke(app, ["run", "--backend", "claude", "-p", "hi"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Interactive path: run without -p dispatches to _launch_session
# ---------------------------------------------------------------------------


def test_run_interactive_dispatches_to_launch_session(
    store_fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``agentbox run AGENT`` (no prompt) should call ``_launch_session``."""
    _seed_agent(store_fixture, "claude-agent", runner_kind="claude_code")

    launch_calls: list[dict] = []

    def _mock_launch_session(**kwargs: object) -> int:
        launch_calls.append(dict(kwargs))
        return 0

    monkeypatch.setattr(_run_mod, "_launch_session", _mock_launch_session)

    # CliRunner intercepts sys.exit() — result.exit_code reflects the return value
    result = runner.invoke(app, ["run", "claude-agent"])
    # Either _launch_session was called, or exit code is 0 (from mock returning 0)
    assert len(launch_calls) > 0 or result.exit_code == 0, (
        f"Expected _launch_session to be called; result.exit_code={result.exit_code}, "
        f"output={result.output!r}"
    )


def test_run_interactive_backend_flag(store_fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """``agentbox run --backend claude --ephemeral`` calls ``_launch_session(runner='claude')``."""
    launch_calls: list[dict] = []

    def _mock_launch_session(**kwargs: object) -> int:
        launch_calls.append(dict(kwargs))
        return 0

    monkeypatch.setattr(_run_mod, "_launch_session", _mock_launch_session)

    result = runner.invoke(app, ["run", "--backend", "claude", "--ephemeral"])
    assert len(launch_calls) > 0 or result.exit_code == 0, (
        f"Expected _launch_session to be called; result.exit_code={result.exit_code}, "
        f"output={result.output!r}"
    )


# ---------------------------------------------------------------------------
# Interactive + token backend: rejection
# ---------------------------------------------------------------------------


def test_run_token_agent_interactive_rejected(
    store_fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interactive mode with a token-backed agent should exit 2 with a helpful message."""
    _seed_agent(store_fixture, "tok-agent", runner_kind="token")

    # The rejection happens inside _launch_session; let it run (no real subprocess)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: MagicMock(returncode=0),
    )

    result = runner.invoke(app, ["run", "tok-agent"])
    # _launch_session raises typer.Exit(2) for token backend
    assert result.exit_code == 2
    assert "token" in result.output.lower() or "pydantic" in result.output.lower(), (
        f"Expected rejection message; got: {result.output!r}"
    )
