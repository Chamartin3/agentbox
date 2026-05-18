"""Tests for executor runner profile resolution (Phase 13c).

Tests the integration between RunnerProfileResolver and RunExecutor,
covering precedence rules, profile binding, and run record persistence.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from agentbox.api.events import DoneEvent, RunEvent, TextEvent
from agentbox.config import Settings
from agentbox.core.agent.profiles import RunnerProfileResolver
from agentbox.core.data import SessionStore
from agentbox.core.data.manifest import AgentDef, RunnerSpec
from agentbox.core.data.runner_profiles import RunnerProfileCreate
from agentbox.core.deprecated.definitions import DefinitionLoader
from agentbox.core.run.backends.base import RenderedConfig
from agentbox.core.run.executor import RunExecutor

# ============================================================================
# Minimal BackendAdapter for executor tests
# ============================================================================


class _EchoBackend:
    """Minimal BackendAdapter — yields TextEvent then successful DoneEvent."""

    name = "echo_backend"

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: Any = None,
        creds: Any = None,
        runner_config: Any = None,
    ) -> RenderedConfig:
        return RenderedConfig(argv=["true"], cwd=workdir)

    async def run(
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        yield TextEvent(run_id=run_id, text="hello")
        yield DoneEvent(run_id=run_id, ok=True, output="hello")


# ============================================================================
# Helpers
# ============================================================================


def _settings(tmp_path: Path) -> Settings:
    """Build test settings."""
    return Settings(
        manifest_path=tmp_path / "manifest.toml",
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        port=0,
        host="127.0.0.1",
        agents_dir=None,
        agents_bundle_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
    )


def _register_backend(name: str, adapter_cls: type) -> None:
    """Register a fake backend for testing."""
    import agentbox.core.agent.plugins as plugins

    plugins.backends()  # warm cache
    plugins._BACKEND_CLASSES[name] = adapter_cls  # type: ignore[index]


def _fake_agent(agent_id: str) -> AgentDef:
    """Build a minimal AgentDef for testing."""
    return AgentDef(
        id=agent_id,
        runner=RunnerSpec(kind="claude_code"),
    )


# ============================================================================
# Pure Resolver Tests (no backend execution)
# ============================================================================


class TestResolverPureLogic:
    """Tests that target the resolver directly without spinning full RunExecutor."""

    def test_per_run_runner_config_wins(self, tmp_path: Path) -> None:
        """Per-run runner_config dict takes precedence over all profiles."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")
        resolver = RunnerProfileResolver()

        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=None,
            runner_config={
                "backend": "token",
                "model": "openai:gpt-4o",
                "timeout_seconds": 90,
            },
            backend_override=None,
            timeout_seconds=None,
        )

        assert config.source == "run_override"
        assert config.backend == "token"
        assert config.model == "openai:gpt-4o"
        assert config.timeout_seconds == 90

    def test_per_run_runner_profile_wins_over_agent_binding(
        self, tmp_path: Path
    ) -> None:
        """Per-run runner_profile_id beats agent-bound profile."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")

        # Create two profiles
        profile1 = store.create_runner_profile(
            RunnerProfileCreate(
                id="profile-1",
                name="Profile 1",
                backend="claude_code",
                model="claude-3.5-sonnet",
            )
        )
        profile2 = store.create_runner_profile(
            RunnerProfileCreate(
                id="profile-2",
                name="Profile 2",
                backend="token",
                model="openai:gpt-4o",
            )
        )

        # Bind profile1 to agent
        store.set_agent_runner_profile(agent.id, profile1.id)

        # Resolve with explicit profile2 request
        resolver = RunnerProfileResolver()
        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=profile2.id,
            runner_config=None,
            backend_override=None,
            timeout_seconds=None,
        )

        assert config.source == "run_profile"
        assert config.backend == "token"
        assert config.model == "openai:gpt-4o"
        assert config.profile_id == profile2.id

    def test_agent_bound_profile_wins_over_legacy(self, tmp_path: Path) -> None:
        """Agent-bound profile beats legacy agent.runner spec."""
        store = SessionStore(tmp_path / "db.sqlite")

        # Create agent with legacy runner spec
        agent = AgentDef(
            id="test-agent",
            runner=RunnerSpec(kind="claude_code", model="claude-3-sonnet"),
        )

        # Create and bind a profile
        profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="profile-1",
                name="Profile 1",
                backend="token",
                model="openai:gpt-4o",
            )
        )
        store.set_agent_runner_profile(agent.id, profile.id)

        # Resolve without explicit profile request
        resolver = RunnerProfileResolver()
        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=None,
            runner_config=None,
            backend_override=None,
            timeout_seconds=None,
        )

        # Should use bound profile, not legacy runner
        assert config.source == "agent_profile"
        assert config.backend == "token"
        assert config.model == "openai:gpt-4o"

    def test_system_default_used_when_no_binding(self, tmp_path: Path) -> None:
        """System default profile is used when agent has no binding."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")

        # Create system default profile
        default_profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="system-default",
                name="System Default",
                backend="token",
                model="openai:gpt-3.5-turbo",
                is_system_default=True,
            )
        )

        # Resolve without explicit profile or agent binding
        resolver = RunnerProfileResolver()
        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=None,
            runner_config=None,
            backend_override=None,
            timeout_seconds=None,
        )

        assert config.source == "system_default"
        assert config.backend == "token"
        assert config.profile_id == default_profile.id

    def test_no_profile_does_not_fall_back_to_agent_runner(self, tmp_path: Path) -> None:
        """Legacy agent.runner is not a dispatch fallback."""
        store = SessionStore(tmp_path / "db.sqlite")

        agent = AgentDef(
            id="test-agent",
            runner=RunnerSpec(
                kind="claude_code",
                model="claude-3-opus",
                timeout_seconds=180,
            ),
        )

        resolver = RunnerProfileResolver()
        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=None,
            runner_config=None,
            backend_override=None,
            timeout_seconds=None,
        )

        assert config.source == "run_override"
        assert config.backend is None
        assert config.model is None
        assert config.timeout_seconds is None

    def test_disabled_explicit_profile_raises(self, tmp_path: Path) -> None:
        """Requesting a disabled profile explicitly raises ValueError."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")

        # Create a disabled profile
        profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="disabled-profile",
                name="Disabled",
                backend="token",
                is_enabled=False,
            )
        )

        resolver = RunnerProfileResolver()
        with pytest.raises(ValueError, match="disabled"):
            resolver.resolve(
                agent=agent,
                store=store,
                runner_profile_id=profile.id,
                runner_config=None,
                backend_override=None,
                timeout_seconds=None,
            )

    def test_disabled_agent_bound_profile_falls_through(
        self, tmp_path: Path
    ) -> None:
        """Disabled agent-bound profile falls through to system default."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")

        # Create disabled agent-bound profile
        disabled_profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="disabled",
                name="Disabled",
                backend="token",
                is_enabled=False,
            )
        )
        store.set_agent_runner_profile(agent.id, disabled_profile.id)

        # Create system default profile
        default_profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="default",
                name="Default",
                backend="claude_code",
                is_system_default=True,
            )
        )

        resolver = RunnerProfileResolver()
        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=None,
            runner_config=None,
            backend_override=None,
            timeout_seconds=None,
        )

        # Should skip disabled agent profile and use system default
        assert config.source == "system_default"
        assert config.backend == "claude_code"
        assert config.profile_id == default_profile.id

    def test_unknown_backend_raises(self, tmp_path: Path) -> None:
        """Requesting unknown backend via runner_config raises ValueError."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")

        resolver = RunnerProfileResolver()
        with pytest.raises(ValueError, match="unknown backend"):
            resolver.resolve(
                agent=agent,
                store=store,
                runner_profile_id=None,
                runner_config={"backend": "not_a_real_backend"},
                backend_override=None,
                timeout_seconds=None,
            )

    def test_per_run_timeout_overrides_profile(self, tmp_path: Path) -> None:
        """Per-run timeout_seconds overrides profile default (no profile timeout)."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")

        profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="profile",
                name="Profile",
                backend="claude_code",
            )
        )

        resolver = RunnerProfileResolver()
        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=profile.id,
            runner_config=None,
            backend_override=None,
            timeout_seconds=120,
        )

        assert config.profile_id == profile.id
        assert config.timeout_seconds == 120  # Override wins

    def test_runner_config_with_params_and_headers(self, tmp_path: Path) -> None:
        """Per-run runner_config can include params and headers."""
        store = SessionStore(tmp_path / "db.sqlite")
        agent = _fake_agent("test-agent")

        resolver = RunnerProfileResolver()
        config = resolver.resolve(
            agent=agent,
            store=store,
            runner_profile_id=None,
            runner_config={
                "backend": "token",
                "model": "openai:gpt-4o",
                "params": {"temperature": 0.7},
                "headers": {"X-Custom": "value"},
            },
            backend_override=None,
            timeout_seconds=None,
        )

        assert config.source == "run_override"
        assert config.params == {"temperature": 0.7}
        assert config.headers == {"X-Custom": "value"}


# ============================================================================
# Executor Integration Tests
# ============================================================================


class TestExecutorRunnerProfiles:
    """Full-stack executor tests with profile resolution."""

    def test_executor_persists_runner_profile_id_on_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Executor persists runner_profile_id to runs table on execution."""
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        settings = _settings(tmp_path)
        store = SessionStore(settings.db_path)
        executor = RunExecutor(store, settings, DefinitionLoader(settings.project_root))

        # Register fake backend
        _register_backend("echo_backend", _EchoBackend)

        # Create an agent
        agent = _fake_agent("test-agent")

        # Create a runner profile
        profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="test-profile",
                name="Test Profile",
                backend="echo_backend",
            )
        )

        # Bind profile to agent
        store.set_agent_runner_profile(agent.id, profile.id)

        # Execute the run
        async def go() -> str:
            rid = await executor.execute(
                agent,
                input_="test input",
                # No explicit runner_profile_id or runner_config
                # Should resolve to bound profile
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())

        # Verify the run record has the profile_id
        rec = store.get_run(rid)
        assert rec is not None
        assert rec.status == "ok"
        assert rec.runner_profile_id == profile.id

    def test_executor_with_explicit_runner_profile_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Executor resolves explicit per-run runner_profile_id."""
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        settings = _settings(tmp_path)
        store = SessionStore(settings.db_path)
        executor = RunExecutor(store, settings, DefinitionLoader(settings.project_root))

        _register_backend("echo_backend", _EchoBackend)

        agent = _fake_agent("test-agent")

        # Create two profiles
        profile_a = store.create_runner_profile(
            RunnerProfileCreate(
                id="profile-a",
                name="Profile A",
                backend="echo_backend",
            )
        )
        profile_b = store.create_runner_profile(
            RunnerProfileCreate(
                id="profile-b",
                name="Profile B",
                backend="echo_backend",
            )
        )

        # Bind profile_a to agent
        store.set_agent_runner_profile(agent.id, profile_a.id)

        # Execute with explicit request for profile_b
        async def go() -> str:
            rid = await executor.execute(
                agent,
                input_="test input",
                runner_profile=profile_b.id,
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())

        # Verify the run used profile_b (override)
        rec = store.get_run(rid)
        assert rec is not None
        assert rec.runner_profile_id == profile_b.id

    def test_executor_with_runner_config_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Executor resolves per-run runner_config dict (highest precedence)."""
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        settings = _settings(tmp_path)
        store = SessionStore(settings.db_path)
        executor = RunExecutor(store, settings, DefinitionLoader(settings.project_root))

        _register_backend("echo_backend", _EchoBackend)

        agent = _fake_agent("test-agent")

        # Create a bound profile that would otherwise be used
        profile = store.create_runner_profile(
            RunnerProfileCreate(
                id="bound-profile",
                name="Bound",
                backend="echo_backend",
            )
        )
        store.set_agent_runner_profile(agent.id, profile.id)

        # Execute with runner_config override (should take precedence)
        async def go() -> str:
            rid = await executor.execute(
                agent,
                input_="test input",
                runner_config={"backend": "echo_backend"},
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())

        # runner_config doesn't create a profile entry; it's a transient override
        # The run record should still reflect the resolution source
        rec = store.get_run(rid)
        assert rec is not None
        assert rec.status == "ok"
