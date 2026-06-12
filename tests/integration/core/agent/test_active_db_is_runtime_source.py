"""Active version is the single source of truth at runtime.

The runner timeout drift bug (`stage.draft_fixer` died at 120s while the
active version said 400s) had two coupled causes:

1. The claude_code backend adapter hardcoded a 120s timeout instead of
   propagating ``agent.runner.timeout_seconds`` into ``RenderedConfig``.
2. There was no test guarding that the value the backend renders is the
   value carried on the active ``AgentDef``.

These tests pin the contract: whatever the active ``AgentDef`` holds for
``runner.timeout_seconds`` and ``runner.model`` must show up unchanged in
the backend's ``RenderedConfig`` — for every shipped backend. If a future
backend forgets to forward a field, the test fails before it reaches a
real run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.engines.backends.claude_code import ClaudeCodeBackend
from agentbox.core.engines.backends.opencode import OpenCodeBackend

_CLAUDE_CODE = "claude_code"
_OPENCODE = "opencode"

_DEFAULT_AGENT_TIMEOUT = 1200


def _agent(
    runner_kind: str, timeout: int, model: str | None = "haiku"
) -> AgentDef:
    return AgentDef(
        id="stage.example",
        runner=RunnerSpec(kind=runner_kind, model=model, timeout_seconds=timeout),
    )


@pytest.mark.parametrize(
    "runner_kind,backend_cls",
    [
        ("claude_code", ClaudeCodeBackend),
        ("opencode", OpenCodeBackend),
    ],
)
def test_backend_render_propagates_active_timeout(
    tmp_path: Path, runner_kind: str, backend_cls
) -> None:
    """The backend's RenderedConfig carries the active version's timeout.

    Regression: claude_code backend used to pass a literal ``120`` into
    ``_run_claude`` regardless of what the active config said, so runs
    silently died at 2 minutes even when the agent was configured for
    longer. ``agent_meta["timeout_seconds"]`` is now the contract every
    backend honors.
    """
    agent = _agent(runner_kind, timeout=400)
    rendered = backend_cls().render(agent, tmp_path)

    assert rendered.agent_meta.get("timeout_seconds") == 400, (
        f"{runner_kind} backend dropped timeout_seconds on the floor — "
        "the value the runner enforces must come from the active config"
    )


def test_claude_backend_render_propagates_active_model(tmp_path: Path) -> None:
    """Model from the active config reaches the claude CLI argv.

    Same single-source-of-truth contract as the timeout test, applied to
    the model selector — if the active version says ``sonnet``, the
    rendered argv must include ``--model sonnet``.
    """
    agent = _agent("claude_code", timeout=300, model="sonnet")
    rendered = ClaudeCodeBackend().render(agent, tmp_path)

    assert "--model" in rendered.argv
    idx = rendered.argv.index("--model")
    assert rendered.argv[idx + 1] == "sonnet"


def test_config_change_invalidates_render_digest(tmp_path: Path) -> None:
    """A timeout change must produce a different render digest.

    ``render.digest`` is what the run-config cache keys on — if the
    digest doesn't change when the active config does, a stale run dir
    is reused with the old timeout.
    """
    first = ClaudeCodeBackend().render(_agent("claude_code", 120), tmp_path)
    second = ClaudeCodeBackend().render(_agent("claude_code", 600), tmp_path)

    assert first.agent_meta["timeout_seconds"] == 120
    assert second.agent_meta["timeout_seconds"] == 600
    assert second.digest != first.digest


@pytest.mark.parametrize(
    "runner_kind,backend_cls",
    [
        ("claude_code", ClaudeCodeBackend),
        ("opencode", OpenCodeBackend),
    ],
)
def test_active_version_always_overrides_default_timeout(
    tmp_path: Path, runner_kind: str, backend_cls
) -> None:
    """The active version's timeout must always override the default.

    The agent's runner config is the single source of truth for
    timeout. Any agent rendered through a backend must populate
    ``agent_meta["timeout_seconds"]`` with the agent's own value — never
    leave it unset. We pick an explicit value distinct from the
    ``RunnerSpec`` default so a regression that drops the field would
    be caught.
    """
    explicit_timeout = _DEFAULT_AGENT_TIMEOUT + 137
    agent = _agent(runner_kind, timeout=explicit_timeout)
    rendered = backend_cls().render(agent, tmp_path)

    assert "timeout_seconds" in rendered.agent_meta, (
        f"{runner_kind} backend must always set agent_meta['timeout_seconds'] "
        "from the active config — never leave the runner to fall back to the default"
    )
    assert rendered.agent_meta["timeout_seconds"] == explicit_timeout
    assert rendered.agent_meta["timeout_seconds"] != _DEFAULT_AGENT_TIMEOUT, (
        "active version's value must override the RunnerSpec default; if these "
        "match by coincidence the test is not exercising the override path"
    )
