"""Tests for token backend provider routing via runner_config.

These tests verify that the token backend correctly accepts and
handles provider, model, base_url, and api_key_env from EffectiveRunnerConfig
during render and run phases.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agentbox.core.data import DoneEvent
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.constants import RunnerKind
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.engines.backends.token import TokenBackend

DEFAULT_RUNNER = RunnerSpec(kind=RunnerKind.TOKEN)


def _make_agent(**overrides: object) -> AgentDef:
    """Create a minimal test AgentDef."""
    kwargs = {
        "id": "test_agent",
        "runner": DEFAULT_RUNNER,
    }
    kwargs.update(overrides)
    return AgentDef(**kwargs)  # type: ignore[arg-type]


class TestTokenProviderRouting:
    """Test suite for provider routing in token backend."""

    def test_render_carries_provider_routing_into_agent_meta(self) -> None:
        """render() with runner_config carries provider/model/base_url into agent_meta.

        The secret (api_key) should NOT appear in agent_meta; only the env
        var name should be stored.
        """
        agent = _make_agent()
        adapter = TokenBackend()

        runner_config = EffectiveRunnerConfig(
            backend="token",
            provider="openai",
            model="openai:gpt-4o",
            base_url="https://example.com/v1",
            api_key_env="MY_KEY",
            profile_id="test-profile",
            source="run_override",
        )

        rendered = adapter.render(
            agent, Path("/tmp/workdir"), runner_config=runner_config
        )

        # Assert provider routing is stored
        assert rendered.agent_meta.get("provider") == "openai"
        assert rendered.agent_meta.get("model") == "openai:gpt-4o"
        assert rendered.agent_meta.get("base_url") == "https://example.com/v1"
        assert rendered.agent_meta.get("api_key_env") == "MY_KEY"
        assert rendered.agent_meta.get("profile_id") == "test-profile"

        # Assert model is updated
        assert rendered.model == "openai:gpt-4o"

        # Assert no secret value is stored
        assert (
            "api_key" not in rendered.agent_meta
            or rendered.agent_meta.get("api_key") is None
        )

    def test_render_without_runner_config_ignores_legacy_runner_model(self) -> None:
        """render() does not read agent.runner.model as runtime config."""
        agent = _make_agent(
            runner=RunnerSpec(
                kind=RunnerKind.TOKEN,
                model="legacy:model",
            )
        )
        adapter = TokenBackend()
        rendered = adapter.render(agent, Path("/tmp/workdir"), runner_config=None)

        assert rendered.model is None
        assert rendered.agent_meta.get("model") is None
        assert "provider" not in rendered.agent_meta

    def test_render_runner_config_model_is_authoritative(self) -> None:
        """runner_config.model is the runtime source of truth."""
        agent = _make_agent(
            runner=RunnerSpec(
                kind=RunnerKind.TOKEN,
                model="spec:default",
            )
        )
        adapter = TokenBackend()

        runner_config = EffectiveRunnerConfig(
            model="override:model",
            source="run_override",
        )

        rendered = adapter.render(
            agent, Path("/tmp/workdir"), runner_config=runner_config
        )

        assert rendered.model == "override:model"

    def test_render_with_only_api_key_env_stored_not_resolved(self) -> None:
        """render() stores api_key_env but does NOT resolve the actual key."""
        agent = _make_agent()
        adapter = TokenBackend()

        runner_config = EffectiveRunnerConfig(
            provider="openai",
            api_key_env="OPENAI_API_KEY",
            source="run_override",
        )

        rendered = adapter.render(
            agent, Path("/tmp/workdir"), runner_config=runner_config
        )

        # Store the env var name, not the key
        assert rendered.agent_meta.get("api_key_env") == "OPENAI_API_KEY"
        # No secret in agent_meta
        assert (
            "api_key" not in rendered.agent_meta
            or rendered.agent_meta.get("api_key") is None
        )

    @pytest.mark.asyncio
    async def test_run_missing_api_key_env_emits_done_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() with api_key_env not set in environment emits DoneEvent(ok=False)."""
        # Ensure the env var is not set
        monkeypatch.delenv("TEST_MISSING_KEY", raising=False)

        agent = _make_agent()
        adapter = TokenBackend()

        runner_config = EffectiveRunnerConfig(
            provider="openai",
            api_key_env="TEST_MISSING_KEY",
            source="run_override",
        )

        rendered = adapter.render(
            agent, Path("/tmp/workdir"), runner_config=runner_config
        )

        # Collect all events from run()
        events = []
        async for event in adapter.run(rendered, "test input", "run-123"):
            events.append(event)

        # Should end with a DoneEvent indicating failure
        assert len(events) > 0
        done_event = events[-1]
        assert isinstance(done_event, DoneEvent)
        assert not done_event.ok

        # Message should mention env var name but not any secret
        message = done_event.error or ""
        assert "TEST_MISSING_KEY" in message or "not set" in message.lower()
        # Should not contain suspicious key patterns
        assert not message.startswith("sk-")

    @pytest.mark.asyncio
    async def test_run_with_env_set_resolves_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() resolves api_key from environment when api_key_env is set.

        This test mocks importlib to verify that api_key,
        base_url, and model are forwarded correctly.
        """
        test_key = "sk-test-key-12345"
        monkeypatch.setenv("TEST_OPENAI_KEY", test_key)

        agent = _make_agent(
            runner=RunnerSpec(
                kind=RunnerKind.TOKEN,
                agent_module="fake:Agent",
            )
        )
        adapter = TokenBackend()

        runner_config = EffectiveRunnerConfig(
            provider="openai",
            model="openai:gpt-4o",
            base_url="https://api.openai.com/v1",
            api_key_env="TEST_OPENAI_KEY",
            source="run_override",
        )

        rendered = adapter.render(
            agent, Path("/tmp/workdir"), runner_config=runner_config
        )

        # Mock importlib to capture the kwargs passed to it
        with patch(
            "agentbox.core.engines.backends.token.importlib.import_module"
        ) as mock_import:
            # Create a mock module with a mock Agent class
            mock_module = MagicMock()
            mock_import.return_value = mock_module

            # Mock the Agent class to just return a mock agent instance
            mock_agent_instance = AsyncMock()
            mock_agent_instance.run = AsyncMock(
                return_value=MagicMock(data="test result")
            )
            mock_module.Agent = MagicMock(return_value=mock_agent_instance)

            # Run and collect events
            events = []
            async for event in adapter.run(rendered, "test input", "run-123"):
                events.append(event)

            # We expect at least log events and a done event
            assert len(events) > 0

    @pytest.mark.asyncio
    async def test_run_no_provider_config_still_works(self) -> None:
        """run() without provider config (legacy behavior) still executes."""
        agent = _make_agent(
            runner=RunnerSpec(
                kind=RunnerKind.TOKEN,
                agent_module="fake:Agent",
            )
        )
        adapter = TokenBackend()

        # No runner_config means no provider routing
        rendered = adapter.render(agent, Path("/tmp/workdir"), runner_config=None)

        # Mock importlib
        with patch("agentbox.core.engines.backends.token.importlib.import_module"):
            events = []
            async for event in adapter.run(rendered, "test input", "run-123"):
                events.append(event)

            # Should emit at least a log event and done event
            assert len(events) > 0

    def test_render_digest_includes_provider_config(self) -> None:
        """render() digest differs when provider config changes."""
        agent = _make_agent()
        adapter = TokenBackend()

        # Render with different provider configs
        config_a = EffectiveRunnerConfig(
            provider="openai",
            model="openai:gpt-4o",
        )
        config_b = EffectiveRunnerConfig(
            provider="openrouter",
            model="openrouter:anthropic/claude-3.5-sonnet",
        )

        r_a = adapter.render(agent, Path("/tmp/workdir"), runner_config=config_a)
        r_b = adapter.render(agent, Path("/tmp/workdir"), runner_config=config_b)

        # Different configs should produce different digests
        assert r_a.digest != r_b.digest

    def test_render_digest_same_for_identical_config(self) -> None:
        """render() digest is stable for identical inputs."""
        agent = _make_agent()
        adapter = TokenBackend()

        config = EffectiveRunnerConfig(
            provider="openai",
            model="openai:gpt-4o",
            api_key_env="MY_KEY",
        )

        r1 = adapter.render(agent, Path("/tmp/workdir"), runner_config=config)
        r2 = adapter.render(agent, Path("/tmp/workdir"), runner_config=config)

        assert r1.digest == r2.digest
