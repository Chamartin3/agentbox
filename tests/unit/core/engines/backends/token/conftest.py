"""Fixtures for the token backend adapter tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from agentbox.core.db import AgentDef


@pytest.fixture
def make_token_agent(make_backend_agent) -> Callable[..., AgentDef]:
    """Factory for a token AgentDef carrying the ``_config_json`` python shim.

    Wraps the shared ``make_backend_agent`` factory and attaches the
    ``python`` config block the token backend reads, derived from the
    resolved runner so it stays in sync with ``**overrides``.
    """

    def _make(**overrides: object) -> AgentDef:
        agent = make_backend_agent(**overrides)
        agent.__dict__["_config_json"] = {
            "python": {
                "agent_module": agent.runner.agent_module,
                "deps_factory": agent.runner.deps_factory,
                "output_schema_path": agent.runner.output_schema_path,
            },
        }
        return agent

    return _make


@pytest.fixture
def collect_events() -> Callable[[AsyncIterator[object]], Awaitable[list[object]]]:
    """Drain an async event iterator into a list."""

    async def _collect(agen: AsyncIterator[object]) -> list[object]:
        return [ev async for ev in agen]

    return _collect
