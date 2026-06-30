"""Unit tests for agentbox.core.execution.retry.

Covers:
- build_retry_prompt  — exact string format that operators grep in runbooks
- build_error_retry_prompt — exact string format for error-recovery prompts
- maybe_load_output_file — output.json fallback logic incl. missing / malformed
- pump_into_session    — event routing from backend stream to RunStreamSession
- RetryOrchestrator.execute — multi-attempt loop: success, error-retry,
  validation-retry, and deadline/timeout paths
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.core.events import DoneEvent, RunEvent, TextEvent
from agentbox.core.engines.contracts.base import BackendAdapter, RenderedConfig
from agentbox.core.execution.observability.stream import CaptureSession
from agentbox.core.execution.retry import (
    RetryOrchestrator,
    RetryOutcome,
    build_error_retry_prompt,
    build_retry_prompt,
    maybe_load_output_file,
    pump_into_session,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class _StubBackend(BackendAdapter):
    """Minimal backend yielding fixed output then DoneEvent."""

    name = "stub"

    def __init__(
        self,
        output: str | None = "result",
        ok: bool = True,
        error: str | None = None,
    ) -> None:
        self._output = output
        self._ok = ok
        self._error = error

    def render(self, agent, workdir, **kw) -> RenderedConfig:
        return RenderedConfig()

    async def run(
        self, rendered: RenderedConfig, input_: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        if self._output:
            yield TextEvent(run_id=run_id, text=self._output, role="assistant")
        yield DoneEvent(run_id=run_id, ok=self._ok, error=self._error)


class _MultiResultBackend(BackendAdapter):
    """Backend returning a pre-configured sequence of (output, ok, error) tuples.

    Records each input received so tests can assert on prompt construction.
    """

    name = "multi-result"

    def __init__(
        self, results: list[tuple[str | None, bool, str | None]]
    ) -> None:
        self._results = list(results)
        self._call_count = 0
        self.received_inputs: list[str] = []

    def render(self, agent, workdir, **kw) -> RenderedConfig:
        return RenderedConfig()

    async def run(
        self, rendered: RenderedConfig, input_: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        self.received_inputs.append(input_)
        output, ok, error = self._results[self._call_count]
        self._call_count += 1
        if output:
            yield TextEvent(run_id=run_id, text=output, role="assistant")
        yield DoneEvent(run_id=run_id, ok=ok, error=error)


class _NoDoneBackend(BackendAdapter):
    """Backend that never emits DoneEvent — simulates a broken stream."""

    name = "no-done"

    def render(self, agent, workdir, **kw) -> RenderedConfig:
        return RenderedConfig()

    async def run(
        self, rendered: RenderedConfig, input_: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        yield TextEvent(run_id=run_id, text="partial", role="assistant")
        # Intentionally no DoneEvent.


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_orchestrator(
    adapter: BackendAdapter,
    tmp_path: Path,
) -> RetryOrchestrator:
    """Return a RetryOrchestrator wired to ``adapter`` with minimal deps."""
    agent = MagicMock()
    agent.id = "test-agent"
    return RetryOrchestrator(
        adapter=adapter,
        rendered=RenderedConfig(),
        agent=agent,
        composed=None,
        workdir=tmp_path,
        store=None,
        project_root=tmp_path,
    )


def _make_validation_result(
    ok: bool, error: str = "schema error", engine: str = "both"
) -> MagicMock:
    result = MagicMock()
    result.ok = ok
    result.error = error
    result.engine = engine
    return result


async def _execute(
    orchestrator: RetryOrchestrator,
    session: CaptureSession,
    *,
    initial_input: str = "do the task",
    max_attempts: int = 1,
    error_retries_left: int = 0,
    validation_retries_left: int = 0,
    timeout_seconds: int = 30,
    has_schema: bool = False,
    validation_mode: str = "off",
    deadline: float | None = None,
) -> RetryOutcome:
    if deadline is None:
        deadline = asyncio.get_event_loop().time() + timeout_seconds
    return await orchestrator.execute(
        initial_input=initial_input,
        max_attempts=max_attempts,
        error_retries_left=error_retries_left,
        validation_retries_left=validation_retries_left,
        timeout_seconds=timeout_seconds,
        deadline=deadline,
        has_schema=has_schema,
        validation_mode=validation_mode,
        session=session,
    )


# --------------------------------------------------------------------------- #
# build_retry_prompt
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_retry_prompt_includes_original_input() -> None:
    """Original input appears verbatim so the agent retains its task context."""
    # Arrange
    original_input = "classify the document"

    # Act
    result = build_retry_prompt(original_input, "bad output", "missing field x")

    # Assert
    assert original_input in result


@pytest.mark.unit
def test_retry_prompt_includes_previous_output() -> None:
    """Previous output is embedded so the agent can see what it got wrong."""
    # Arrange
    previous_output = '{"score": "high"}'

    # Act
    result = build_retry_prompt("task", previous_output, "score must be numeric")

    # Assert
    assert previous_output in result


@pytest.mark.unit
def test_retry_prompt_includes_validation_error() -> None:
    """Validation error text is surfaced so the agent can correct its output."""
    # Arrange
    validation_error = "required property 'name' is missing"

    # Act
    result = build_retry_prompt("task", "prev", validation_error)

    # Assert
    assert validation_error in result


@pytest.mark.unit
def test_retry_prompt_has_fix_it_section() -> None:
    """'FIX IT' section must appear — operators grep this in runbooks."""
    # Arrange / Act
    result = build_retry_prompt("task", "prev", "error")

    # Assert
    assert "FIX IT" in result


@pytest.mark.unit
def test_retry_prompt_has_failed_validation_header() -> None:
    """'PREVIOUS ATTEMPT FAILED VALIDATION' header must be stable — UIs parse it."""
    # Arrange / Act
    result = build_retry_prompt("task", "prev", "error")

    # Assert
    assert "PREVIOUS ATTEMPT FAILED VALIDATION" in result


@pytest.mark.unit
def test_retry_prompt_format_stable() -> None:
    """Exact template shape: drift breaks operator runbooks and test assertions."""
    # Arrange
    original_input = "do the task"
    previous_output = "bad json"
    validation_error = "missing field 'name'"

    # Act
    result = build_retry_prompt(original_input, previous_output, validation_error)

    # Assert
    expected = (
        "do the task\n\n"
        "--- PREVIOUS ATTEMPT FAILED VALIDATION ---\n"
        "Your previous output did not pass validation:\n\n"
        "missing field 'name'\n\n"
        "--- YOUR PREVIOUS OUTPUT ---\n"
        "bad json\n\n"
        "--- FIX IT ---\n"
        "Fix the issues above and produce a corrected output that passes validation."
    )
    assert result == expected


# --------------------------------------------------------------------------- #
# build_error_retry_prompt
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_error_retry_prompt_with_error_and_output() -> None:
    """Both error text and previous output are present when both are provided."""
    # Arrange
    error = "subprocess exited with code 1"
    previous_output = "partial result"

    # Act
    result = build_error_retry_prompt("task", previous_output, error)

    # Assert
    assert error in result
    assert previous_output in result
    assert "YOUR PREVIOUS OUTPUT" in result
    assert "failed with the following error" in result


@pytest.mark.unit
def test_error_retry_prompt_no_previous_output() -> None:
    """When previous_output is None the 'YOUR PREVIOUS OUTPUT' section is omitted."""
    # Arrange
    error = "runner crashed"

    # Act
    result = build_error_retry_prompt("task", None, error)

    # Assert
    assert "YOUR PREVIOUS OUTPUT" not in result
    assert error in result
    assert "FIX IT" in result


@pytest.mark.unit
def test_error_retry_prompt_no_error() -> None:
    """When error is None the 'failed with the following error' section is omitted."""
    # Arrange
    previous_output = "some partial output"

    # Act
    result = build_error_retry_prompt("task", previous_output, None)

    # Assert
    assert "failed with the following error" not in result
    assert previous_output in result
    assert "FIX IT" in result


@pytest.mark.unit
def test_error_retry_prompt_all_none() -> None:
    """Even when both optional args are None the original input and FIX IT remain."""
    # Arrange
    original_input = "analyse the log file"

    # Act
    result = build_error_retry_prompt(original_input, None, None)

    # Assert
    assert original_input in result
    assert "FIX IT" in result
    assert "PREVIOUS ATTEMPT FAILED" in result


# --------------------------------------------------------------------------- #
# maybe_load_output_file
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_maybe_load_returns_current_when_valid_json(tmp_path: Path) -> None:
    """When current is valid JSON it is returned without touching the filesystem."""
    # Arrange
    current = '{"a": 1}'
    # Write an output.json that should be ignored.
    (tmp_path / "output.json").write_text('{"b": 2}', encoding="utf-8")

    # Act
    result = maybe_load_output_file(current, tmp_path)

    # Assert
    assert result == current


@pytest.mark.unit
def test_maybe_load_uses_file_when_current_not_json(tmp_path: Path) -> None:
    """When current is plain text and output.json exists, the file wins."""
    # Arrange
    (tmp_path / "output.json").write_text('{"ok": true}', encoding="utf-8")

    # Act
    result = maybe_load_output_file("plain text", tmp_path)

    # Assert
    assert result == '{"ok": true}'


@pytest.mark.unit
def test_maybe_load_returns_current_when_file_missing(tmp_path: Path) -> None:
    """When current is non-JSON and no output.json exists, current is returned."""
    # Arrange — no output.json written

    # Act
    result = maybe_load_output_file("non-json string", tmp_path)

    # Assert
    assert result == "non-json string"


@pytest.mark.unit
def test_maybe_load_returns_none_when_both_absent(tmp_path: Path) -> None:
    """When current is None and no output.json exists, None is returned."""
    # Arrange — no output.json written

    # Act
    result = maybe_load_output_file(None, tmp_path)

    # Assert
    assert result is None


@pytest.mark.unit
def test_maybe_load_uses_file_when_current_is_empty(tmp_path: Path) -> None:
    """Empty string is treated as absent — output.json is consulted."""
    # Arrange
    (tmp_path / "output.json").write_text('{"status": "done"}', encoding="utf-8")

    # Act
    result = maybe_load_output_file("", tmp_path)

    # Assert
    assert result == '{"status": "done"}'


@pytest.mark.unit
def test_maybe_load_returns_file_json_content(tmp_path: Path) -> None:
    """File content is returned verbatim — callers validate the JSON themselves."""
    # Arrange
    json_content = '{"result": [1, 2, 3], "ok": true}'
    (tmp_path / "output.json").write_text(json_content, encoding="utf-8")

    # Act
    result = maybe_load_output_file("not json", tmp_path)

    # Assert
    assert result == json_content


# --------------------------------------------------------------------------- #
# pump_into_session
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pump_routes_text_event_to_session_accumulator() -> None:
    """TextEvent from the backend is appended to session.output_text."""
    # Arrange
    backend = _StubBackend(output="hello world", ok=True)
    session = CaptureSession(run_id="r1")

    # Act
    result = await pump_into_session(backend, RenderedConfig(), "input", session)

    # Assert
    assert result.ok is True
    assert session.output_text == ["hello world"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pump_done_event_is_not_forwarded_to_session() -> None:
    """DoneEvent is captured as BackendRunResult and NOT emitted into the session."""
    # Arrange
    backend = _StubBackend(output="text", ok=True)
    session = CaptureSession(run_id="r1")

    # Act
    await pump_into_session(backend, RenderedConfig(), "input", session)

    # Assert — no DoneEvent in captured list; session remains open for further events
    assert not any(isinstance(ev, DoneEvent) for ev in session.captured)
    assert session.done_emitted is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pump_returns_not_ok_when_backend_emits_no_done_event() -> None:
    """If the backend stream ends without DoneEvent the default ok=False is returned."""
    # Arrange
    backend = _NoDoneBackend()
    session = CaptureSession(run_id="r1")

    # Act
    result = await pump_into_session(backend, RenderedConfig(), "input", session)

    # Assert
    assert result.ok is False


# --------------------------------------------------------------------------- #
# RetryOrchestrator.execute — success path
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_success_no_schema_returns_ok(tmp_path: Path) -> None:
    """Single successful attempt with no schema configured returns final_ok=True."""
    # Arrange
    backend = _StubBackend(output="answer", ok=True)
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()

    # Act
    outcome = await _execute(orchestrator, session, has_schema=False)

    # Assert
    assert outcome.final_ok is True
    assert outcome.validation_status is None
    assert outcome.final_error is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_success_captures_output_text(tmp_path: Path) -> None:
    """Output text from the backend run is accumulated in the outcome."""
    # Arrange
    backend = _StubBackend(output='{"score": 42}', ok=True)
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()

    # Act
    outcome = await _execute(orchestrator, session, has_schema=False)

    # Assert
    assert outcome.output == '{"score": 42}'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_success_with_schema_sets_validation_status_ok(
    tmp_path: Path,
) -> None:
    """When validation passes, validation_status='ok' and schema_validated_via is set."""
    # Arrange
    backend = _StubBackend(output='{"name": "Alice"}', ok=True)
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    pass_result = _make_validation_result(ok=True, engine="both")

    # Act
    with patch("agentbox.core.execution.retry.validate_output", return_value=pass_result):
        outcome = await _execute(
            orchestrator,
            session,
            has_schema=True,
            validation_mode="strict",
        )

    # Assert
    assert outcome.final_ok is True
    assert outcome.validation_status == "ok"
    assert outcome.schema_validated_via == "both"
    assert outcome.validation_errors is None


# --------------------------------------------------------------------------- #
# RetryOrchestrator.execute — error retry path
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_error_retry_exhausted_returns_not_ok(
    tmp_path: Path,
) -> None:
    """When the backend fails and no error retries remain, final_ok=False."""
    # Arrange
    backend = _StubBackend(output=None, ok=False, error="runner crashed")
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()

    # Act
    outcome = await _execute(
        orchestrator,
        session,
        error_retries_left=0,
        max_attempts=1,
    )

    # Assert
    assert outcome.final_ok is False
    assert outcome.final_error == "runner crashed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_error_retry_succeeds_on_second_attempt(
    tmp_path: Path,
) -> None:
    """A backend error on attempt 1 is recovered when attempt 2 succeeds."""
    # Arrange
    backend = _MultiResultBackend([
        (None, False, "transient error"),  # attempt 0: fail
        ("recovered output", True, None),  # attempt 1: success
    ])
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()

    # Act
    outcome = await _execute(
        orchestrator,
        session,
        error_retries_left=1,
        max_attempts=2,
    )

    # Assert
    assert outcome.final_ok is True
    assert outcome.output == "recovered output"
    assert backend._call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_error_retry_uses_error_retry_prompt(
    tmp_path: Path,
) -> None:
    """Second attempt receives a prompt built from build_error_retry_prompt."""
    # Arrange
    backend = _MultiResultBackend([
        (None, False, "boom"),        # attempt 0: fail with error "boom"
        ("fixed", True, None),        # attempt 1: success
    ])
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    initial_input = "do the task"

    # Act
    await _execute(
        orchestrator,
        session,
        initial_input=initial_input,
        error_retries_left=1,
        max_attempts=2,
    )

    # Assert — second input must be a retry prompt, not the raw original
    assert len(backend.received_inputs) == 2
    second_input = backend.received_inputs[1]
    assert initial_input in second_input
    assert "PREVIOUS ATTEMPT FAILED" in second_input
    assert "boom" in second_input


# --------------------------------------------------------------------------- #
# RetryOrchestrator.execute — validation retry path
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_validation_retry_succeeds_on_second_attempt(
    tmp_path: Path,
) -> None:
    """When validation fails on attempt 1 but passes on attempt 2, outcome is ok."""
    # Arrange
    backend = _MultiResultBackend([
        ('{"a": 1}', True, None),  # attempt 0: backend ok, validation will fail
        ('{"a": 1}', True, None),  # attempt 1: backend ok, validation will pass
    ])
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    fail_result = _make_validation_result(ok=False, error="missing field b")
    pass_result = _make_validation_result(ok=True, engine="both")

    # Act
    with patch(
        "agentbox.core.execution.retry.validate_output",
        side_effect=[fail_result, pass_result],
    ):
        outcome = await _execute(
            orchestrator,
            session,
            has_schema=True,
            validation_mode="strict",
            validation_retries_left=1,
            max_attempts=2,
        )

    # Assert
    assert outcome.final_ok is True
    assert outcome.validation_status == "ok"
    assert backend._call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_validation_exhausted_strict_mode_fails(
    tmp_path: Path,
) -> None:
    """Exhausted validation retries in strict mode marks the run as failed."""
    # Arrange
    backend = _StubBackend(output='{"partial": true}', ok=True)
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    fail_result = _make_validation_result(ok=False, error="required property missing")

    # Act
    with patch(
        "agentbox.core.execution.retry.validate_output",
        return_value=fail_result,
    ):
        outcome = await _execute(
            orchestrator,
            session,
            has_schema=True,
            validation_mode="strict",
            validation_retries_left=0,
            max_attempts=1,
        )

    # Assert
    assert outcome.final_ok is False
    assert outcome.final_status == "failed"
    assert outcome.validation_status == "fail"
    assert "required property missing" in (outcome.final_error or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_validation_exhausted_warn_mode_returns_ok(
    tmp_path: Path,
) -> None:
    """Exhausted validation retries in warn mode leaves final_ok=True."""
    # Arrange
    backend = _StubBackend(output='{"partial": true}', ok=True)
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    fail_result = _make_validation_result(ok=False, error="non-critical warning")

    # Act
    with patch(
        "agentbox.core.execution.retry.validate_output",
        return_value=fail_result,
    ):
        outcome = await _execute(
            orchestrator,
            session,
            has_schema=True,
            validation_mode="warn",
            validation_retries_left=0,
            max_attempts=1,
        )

    # Assert
    assert outcome.final_ok is True
    assert outcome.validation_status == "warn"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_validation_retry_uses_retry_prompt(
    tmp_path: Path,
) -> None:
    """Second attempt receives a prompt built from build_retry_prompt."""
    # Arrange
    initial_input = "produce a report"
    backend = _MultiResultBackend([
        ('{"v": 1}', True, None),  # attempt 0: backend ok, validation fails
        ('{"v": 2}', True, None),  # attempt 1: backend ok, validation passes
    ])
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    fail_result = _make_validation_result(ok=False, error="v must be string")
    pass_result = _make_validation_result(ok=True, engine="both")

    # Act
    with patch(
        "agentbox.core.execution.retry.validate_output",
        side_effect=[fail_result, pass_result],
    ):
        await _execute(
            orchestrator,
            session,
            initial_input=initial_input,
            has_schema=True,
            validation_mode="strict",
            validation_retries_left=1,
            max_attempts=2,
        )

    # Assert — second call input must include the validation failure details
    assert len(backend.received_inputs) == 2
    second_input = backend.received_inputs[1]
    assert initial_input in second_input
    assert "PREVIOUS ATTEMPT FAILED VALIDATION" in second_input
    assert "v must be string" in second_input


# --------------------------------------------------------------------------- #
# RetryOrchestrator.execute — deadline / timeout
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_deadline_already_expired_returns_timeout(
    tmp_path: Path,
) -> None:
    """When the deadline is in the past before attempt 0, the run times out."""
    # Arrange
    backend = _StubBackend(output="answer", ok=True)
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    past_deadline = asyncio.get_event_loop().time() - 1.0

    # Act
    outcome = await _execute(
        orchestrator,
        session,
        deadline=past_deadline,
        max_attempts=1,
        timeout_seconds=30,
    )

    # Assert
    assert outcome.final_ok is False
    assert outcome.final_status == "timeout"
    assert outcome.final_error is not None
    assert "timeout" in outcome.final_error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_timeout_mid_attempt_returns_failure(
    tmp_path: Path,
    make_slow_backend,
) -> None:
    """When the deadline fires during a slow backend run the outcome is a timeout."""
    # Arrange — backend sleeps 5 s; deadline is 50 ms away
    backend = make_slow_backend(sleep_s=5.0)
    orchestrator = _make_orchestrator(backend, tmp_path)
    session = CaptureSession()
    tight_deadline = asyncio.get_event_loop().time() + 0.05

    # Act
    outcome = await _execute(
        orchestrator,
        session,
        deadline=tight_deadline,
        max_attempts=1,
        timeout_seconds=1,
    )

    # Assert
    assert outcome.final_ok is False
    assert outcome.final_status == "timeout"
