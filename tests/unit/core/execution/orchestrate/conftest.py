"""Shared fixtures for orchestrate unit tests.

These express the finalizer's collaborators as injected dependencies:
``finalizer`` is wired to the shared ``mock_store`` fixture, ``patch_dispatch``
neutralises the module-level ``dispatch_completion`` side effect, and
``run_finalize`` drives ``RunFinalizer.finalize`` with sensible defaults so each
test overrides only the field it exercises.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.core.execution.observability.stream.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.finalizer import RunFinalizer
from agentbox.core.execution.orchestrate.steploop import StepResult


@pytest.fixture
def finalizer(mock_store: MagicMock) -> RunFinalizer:
    """RunFinalizer wired to the shared ``mock_store`` fixture (manager params)."""
    return RunFinalizer(
        runs=mock_store.runs,
        usage=mock_store.usage,
        webhook_deliveries=mock_store.webhook_deliveries,
        settings=MagicMock(),
    )


@pytest.fixture
def patch_dispatch() -> Iterator[MagicMock]:
    """Patch ``dispatch_completion`` at its finalizer import site; yield the mock."""
    with patch(
        "agentbox.core.execution.orchestrate.finalizer.dispatch_completion"
    ) as mock_dispatch:
        yield mock_dispatch


@pytest.fixture
def make_agent() -> Callable[..., MagicMock]:
    """Factory for a minimal agent mock (workspace + session_mode)."""

    def _make(workspace: str = "default", session_mode: str = "stateless") -> MagicMock:
        agent = MagicMock()
        agent.workspace = workspace
        agent.session_mode = session_mode
        return agent

    return _make


@pytest.fixture
def make_step_result() -> Callable[..., StepResult]:
    """Factory for a StepResult with a passing default; override via kwargs."""

    def _make(**kwargs: object) -> StepResult:
        defaults: dict = dict(
            final_ok=True,
            final_error=None,
            final_status=None,
            output='{"result": 1}',
            validation_status="ok",
            validation_errors=None,
            schema_validated_via="json-schema",
            session=MagicMock(),
        )
        defaults.update(kwargs)
        return StepResult(**defaults)

    return _make


@pytest.fixture
def run_finalize(
    finalizer: RunFinalizer,
    tmp_path: Path,
    make_agent: Callable[..., MagicMock],
    patch_dispatch: MagicMock,
) -> Callable[..., None]:
    """Call ``finalizer.finalize`` with defaults; override any kwarg.

    Depends on ``patch_dispatch`` so the dispatch side effect is always
    neutralised — tests that assert on dispatch just request ``patch_dispatch``
    too (same instance).
    """

    def _run(**overrides: object) -> None:
        kwargs: dict = dict(
            run_id="run-test",
            agent=make_agent(),
            adapter=MagicMock(spec=[]),
            transcript_path=tmp_path / "transcript.jsonl",
            broadcaster=RunBroadcaster(),
            workdir=tmp_path / "work",
            run_dir=tmp_path / "run",
            step_result=None,
        )
        kwargs.update(overrides)
        finalizer.finalize(**kwargs)  # type: ignore[arg-type]

    return _run
