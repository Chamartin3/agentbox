"""Tests for the backend adapter registry."""

from __future__ import annotations

import pytest
from agentbox.core.agents.plugins import backends
from agentbox.core.engines.backends import get_backend, list_backends


def test_registry_loads_all_entry_points() -> None:
    names = backends()
    assert "claude_code" in names
    assert "opencode" in names
    assert "token" in names


def test_get_backend_returns_instance() -> None:
    adapter = get_backend("claude_code")
    assert hasattr(adapter, "render")
    assert hasattr(adapter, "run")


def test_unknown_backend_raises() -> None:
    with pytest.raises(KeyError, match="no backend adapter"):
        get_backend("nonexistent_backend")


def test_list_backends_includes_all() -> None:
    names = list_backends()
    assert "claude_code" in names
    assert "opencode" in names
    assert "token" in names


def test_backend_adapter_has_name_attr() -> None:
    for name in ("claude_code", "opencode", "token"):
        adapter = get_backend(name)
        assert adapter.name == name


def test_fake_adapter_can_be_registered(monkeypatch) -> None:
    from agentbox.core.engines.backends.base import RenderedConfig

    class FakeBackend:
        name = "fake"

        def render(
            self, agent, workdir, mcp_tools=None, creds=None, runner_config=None
        ) -> RenderedConfig:
            return RenderedConfig(cwd=workdir)

        async def run(self, rendered, input, run_id):
            yield None  # type: ignore[return-value]

    import agentbox.core.agents.plugins as plugins

    plugins._BACKEND_CLASSES = None  # type: ignore[attr-defined]
    with monkeypatch.context() as m:
        m.setitem(plugins.backends(), "fake", FakeBackend)
        adapter = get_backend("fake")
        assert adapter.name == "fake"
