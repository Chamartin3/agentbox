"""Shared fixtures for ``tests/unit/core/agents``."""

from __future__ import annotations

import pytest
from agentbox.core.agents.contract import check_output


@pytest.fixture
def validate_via_config():
    """Run ``check_output`` with ``agent._config_json`` seeded from the
    agent's ``RunnerSpec`` — mirrors how the executor invokes validation.

    Returns a callable ``(output, agent, workdir) -> (ok, error, engine)``.
    """

    def _validate(output, agent, workdir) -> tuple[bool, str, str]:
        agent.__dict__["_config_json"] = {
            "execution": {
                "output_validation_engine": agent.runner.output_validation_engine,
            },
            "python": {"output_schema_path": agent.runner.output_schema_path},
        }
        r = check_output(agent, workdir, output)
        return r.ok, r.error, r.engine

    return _validate
