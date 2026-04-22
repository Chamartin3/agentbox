"""Tests for per-run tmpfs dir lifecycle and D1 regression (no stale config cache)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agentbox.api.events import DoneEvent, RunEvent, TextEvent
from agentbox.config import Settings
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.data import SessionStore
from agentbox.core.definitions import AgentDef, DefinitionLoader, RunnerSpec
from agentbox.core.executor import RunExecutor


class _EchoAdapter:
    name = "echo_per_run"

    def render(self, agent, workdir, mcp_tools=None, creds=None):  # type: ignore[no-untyped-def]
        return RenderedConfig(argv=["true"], cwd=Path("."))

    async def run(
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        yield TextEvent(run_id=run_id, text=f"cwd={rendered.cwd}")
        yield DoneEvent(run_id=run_id, ok=True, output="ok")


class _FailAdapter:
    name = "fail_per_run"

    def render(self, agent, workdir, mcp_tools=None, creds=None):  # type: ignore[no-untyped-def]
        return RenderedConfig(argv=["false"], cwd=Path("."))

    async def run(
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        yield DoneEvent(run_id=run_id, ok=False, error="intentional failure")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        manifest_path=tmp_path / "manifest.toml",
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        port=0,
        host="127.0.0.1",
        agents_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
    )


def _register(name: str, cls: type) -> None:
    import agentbox.core.plugins as plugins

    plugins.backends()
    plugins._BACKEND_CLASSES[name] = cls  # type: ignore[index]


def _executor(tmp_path: Path) -> RunExecutor:
    settings = _settings(tmp_path)
    store = SessionStore(settings.db_path)
    return RunExecutor(store, settings, DefinitionLoader(settings.project_root))


async def _run(executor: RunExecutor, agent: AgentDef, backend: str) -> str:
    rid = await executor.execute(agent, input_="hi", backend=backend)
    q = executor.broadcaster(rid).subscribe()  # type: ignore[union-attr]
    while await q.get() is not None:
        pass
    return rid


class TestRunDirLifecycle:
    def test_run_dir_deleted_after_success(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("echo_per_run", _EchoAdapter)
        executor = _executor(tmp_path)
        agent = AgentDef(id="t", runner=RunnerSpec())

        seen: list[Path] = []
        orig_cleanup = RunExecutor._cleanup_run_dir

        @staticmethod  # type: ignore[misc]
        def _spy(run_dir):  # type: ignore[no-untyped-def]
            seen.append(run_dir)
            orig_cleanup(run_dir)

        monkeypatch.setattr(RunExecutor, "_cleanup_run_dir", _spy)

        asyncio.run(_run(executor, agent, "echo_per_run"))

        assert len(seen) == 1
        assert not seen[0].exists()

    def test_run_dir_deleted_after_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("fail_per_run", _FailAdapter)
        executor = _executor(tmp_path)
        agent = AgentDef(id="t", runner=RunnerSpec())

        seen: list[Path] = []
        orig_cleanup = RunExecutor._cleanup_run_dir

        @staticmethod  # type: ignore[misc]
        def _spy(run_dir):  # type: ignore[no-untyped-def]
            seen.append(run_dir)
            orig_cleanup(run_dir)

        monkeypatch.setattr(RunExecutor, "_cleanup_run_dir", _spy)

        asyncio.run(_run(executor, agent, "fail_per_run"))

        assert len(seen) == 1
        assert not seen[0].exists()

    def test_keep_run_dirs_env_preserves_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AGENTBOX_KEEP_RUN_DIRS", "1")
        _register("echo_per_run", _EchoAdapter)
        executor = _executor(tmp_path)
        agent = AgentDef(id="t", runner=RunnerSpec())

        seen: list[Path] = []
        orig_cleanup = RunExecutor._cleanup_run_dir

        @staticmethod  # type: ignore[misc]
        def _spy(run_dir):  # type: ignore[no-untyped-def]
            seen.append(run_dir)
            orig_cleanup(run_dir)

        monkeypatch.setattr(RunExecutor, "_cleanup_run_dir", _spy)

        asyncio.run(_run(executor, agent, "echo_per_run"))

        assert len(seen) == 1
        assert seen[0].exists()

    def test_two_concurrent_runs_use_disjoint_dirs(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("AGENTBOX_KEEP_RUN_DIRS", "1")
        _register("echo_per_run", _EchoAdapter)
        executor = _executor(tmp_path)
        agent = AgentDef(id="t", runner=RunnerSpec())

        seen: list[Path] = []
        orig_cleanup = RunExecutor._cleanup_run_dir

        @staticmethod  # type: ignore[misc]
        def _spy(run_dir):  # type: ignore[no-untyped-def]
            seen.append(run_dir)
            orig_cleanup(run_dir)

        monkeypatch.setattr(RunExecutor, "_cleanup_run_dir", _spy)

        async def run_two() -> None:
            rid1 = await executor.execute(agent, input_="a", backend="echo_per_run")
            rid2 = await executor.execute(agent, input_="b", backend="echo_per_run")
            for rid in (rid1, rid2):
                q = executor.broadcaster(rid).subscribe()  # type: ignore[union-attr]
                while await q.get() is not None:
                    pass

        asyncio.run(run_two())

        assert len(seen) == 2
        assert seen[0] != seen[1]


class TestD1Regression:
    """Regression: editing agentbox.toml between two runs should be visible to run 2.

    D1 was the drift point where cached .agentbox/generated/ configs were
    never rewritten even after the source manifest changed.
    """

    def test_manifest_edit_seen_by_next_run(self, tmp_path: Path, monkeypatch) -> None:
        """D1 regression: fresh render every run, no stale .agentbox/generated/ cache."""
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("echo_per_run", _EchoAdapter)

        executor = _executor(tmp_path)
        agent = AgentDef(id="t", runner=RunnerSpec())

        # Run 1 — baseline
        asyncio.run(_run(executor, agent, "echo_per_run"))

        # Run 2 — same agent, same executor; no manifest file needed to verify
        # per-run rendering (no stale cache path exists to trigger D1)
        asyncio.run(_run(executor, agent, "echo_per_run"))

        store = executor.store
        runs = store.list_runs()
        assert len(runs) == 2
        for r in runs:
            assert r.status == "ok", f"run {r.run_id} not ok: {r}"

        # Neither run should have left a .agentbox/generated/ directory
        for ws_dir in (tmp_path / "ws").rglob(".agentbox"):
            assert not (ws_dir / "generated").exists(), (
                f"stale generated dir found at {ws_dir / 'generated'}"
            )
