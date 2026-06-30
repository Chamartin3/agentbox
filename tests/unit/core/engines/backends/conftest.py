"""Shared fixtures for backend adapter unit tests.

Replaces the six near-identical module-level helpers with a single
``make_backend_agent`` factory fixture.  Tests key on ``id`` and pass
``runner=RunnerSpec(...)`` explicitly.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from agentbox.core.data import AgentDef, RunnerSpec


@pytest.fixture
def make_backend_agent() -> Callable[..., AgentDef]:
    """Factory for a minimal AgentDef for backend unit tests.

    Returns an AgentDef keyed on ``id``, defaulting
    ``runner=RunnerSpec(kind="token")``.  Pass ``**overrides`` to
    customise any field (including ``runner``, ``id``).

    If ``config_json`` is included in overrides it is stored as
    ``_config_json`` on the instance (used by the claude_code and
    pydantic_ai_adapter tests).
    """

    def _make(**overrides: object) -> AgentDef:
        config_json = overrides.pop("config_json", None)
        kwargs: dict[str, object] = {
            "id": "test_agent",
            "runner": RunnerSpec(kind="token"),
        }
        kwargs.update(overrides)
        agent = AgentDef(**kwargs)  # type: ignore[arg-type]
        if config_json is not None:
            agent.__dict__["_config_json"] = config_json
        return agent

    return _make
