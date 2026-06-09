"""Drive the backend stream and aggregate it into terminal state.

``RunStepLoop`` owns everything between "we have an adapter + rendered
config" and "the run is logically complete (terminal status known)".
It does *not* persist the terminal state — that's the finalizer's job.

The actual per-event work (transcript append, WS broadcast, usage
record, schema validation, retry-on-validation-failure) is handled by
:class:`agentbox.core.execution.retry.RetryOrchestrator` and
:class:`agentbox.core.execution.streaming.session.RunStreamSession`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from agentbox.core.data import UsageEvent
from agentbox.config import Settings
from agentbox.core.agents import AgentRuntimeView
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.constants import RunStatus
from agentbox.core.data import AgentDef, UsageStore
from agentbox.core.engines.backends.base import RenderedConfig
from agentbox.core.execution.retry import RetryOrchestrator
from agentbox.core.execution.streaming.session import RunStreamSession

from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster

if TYPE_CHECKING:
    from agentbox.core.engines.backends.base import BackendAdapter

logger = logging.getLogger(__name__)


# Substring markers that identify expected, agent-level failures (vs.
# unexpected executor/runner crashes). When ``final_error`` matches any
# of these, the run is classified as ``failed`` rather than ``error``.
_FAILED_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "rate limit",
    "rate-limit",
    "rate_limit",
    "ratelimit",
    " 429",
    "429:",
    "quota",
    "overloaded",
    "insufficient_quota",
    "FreeUsageLimitError",
    "CreditsError",
    "AI_APICallError",
    "AuthError",
    "UnauthorizedError",
    "invalid_api_key",
    "invalid api key",
    "authentication_error",
    "authentication error",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectTimeout",
    "ReadTimeout",
    "ECONNREFUSED",
    "ECONNRESET",
    "output validation failed",
    # pydantic-ai surfaces structured-output validation exhaustion as
    # ``UnexpectedModelBehavior: Exceeded maximum output retries (N)`` —
    # the model couldn't produce schema-compliant output. Treat as a
    # validation-shaped failure rather than a runner crash.
    "exceeded maximum output retries",
)


def classify_terminal_error(err: str | None) -> str | None:
    """Map a final error string to ``failed`` when it matches a known
    expected-failure marker (rate-limit, auth, connection, validation).

    Returns ``RunStatus.FAILED.value`` on a match, else ``None`` (caller
    keeps whatever status it already had — typically ``error``).
    """
    if not err:
        return None
    lower = err.lower()
    for marker in _FAILED_ERROR_MARKERS:
        if marker.lower() in lower:
            return RunStatus.FAILED.value
    return None


@dataclass
class StepResult:
    """Outcome of running the backend stream through to completion."""

    final_ok: bool
    final_error: str | None
    final_status: str | None
    output: str | None
    validation_status: str | None
    validation_errors: list[str] | None
    schema_validated_via: str | None
    session: RunStreamSession


class RunStepLoop:
    """Stream-driver that turns a (run, adapter, rendered) into a
    :class:`StepResult` ready for the finalizer.
    """

    def __init__(self, store: UsageStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    async def run(
        self,
        *,
        run_id: str,
        adapter: BackendAdapter,
        rendered: RenderedConfig,
        agent: AgentDef,
        input_: str,
        workdir: Path,
        transcript_path: Path,
        broadcaster: RunBroadcaster,
        effective: EffectiveRunnerConfig | None,
        composed: Any | None,
    ) -> StepResult:
        view = AgentRuntimeView.from_agent(agent, store=self.store)

        error_retries_left = view.max_error_retries or 0
        validation_retries_left = view.max_validation_retries or 0
        max_attempts = 1 + error_retries_left + validation_retries_left

        timeout = (
            effective.timeout_seconds
            if effective is not None and effective.timeout_seconds
            else agent.runner.timeout_seconds
        )

        # ``timeout`` is the per-RUN wall-clock budget, shared across every
        # error/validation retry attempt below — not a per-attempt allowance.
        deadline = asyncio.get_event_loop().time() + timeout

        session = RunStreamSession(
            run_id=run_id,
            broadcaster=broadcaster,
            transcript_path=transcript_path,
        )
        session.add_observer(
            lambda ev: (
                self.store.record_usage(run_id, ev.model_dump())
                if isinstance(ev, UsageEvent)
                else None
            )
        )

        final_ok = False
        final_error: str | None = None
        final_status: str | None = None
        output: str | None = None
        validation_status: str | None = None
        validation_errors: list[str] | None = None
        schema_validated_via: str | None = None

        with session:
            has_schema = bool(
                view.output_schema_path
                or (composed is not None and isinstance(composed.schema, dict))
                or view.json_schema is not None
                or bool(view.validators)
            )
            validation_mode = (
                composed.validation_mode
                if composed is not None and composed.validation_mode is not None
                else "strict"
            )

            orchestrator = RetryOrchestrator(
                adapter=adapter,
                rendered=rendered,
                agent=agent,
                composed=composed,
                workdir=workdir,
                store=self.store,
                project_root=self.settings.project_root,
            )
            outcome = await orchestrator.execute(
                initial_input=input_,
                max_attempts=max_attempts,
                error_retries_left=error_retries_left,
                validation_retries_left=validation_retries_left,
                timeout_seconds=timeout,
                deadline=deadline,
                has_schema=has_schema,
                validation_mode=validation_mode,
                session=session,
            )
            final_ok = outcome.final_ok
            final_error = outcome.final_error
            final_status = outcome.final_status
            output = outcome.output
            validation_status = outcome.validation_status
            validation_errors = outcome.validation_errors
            schema_validated_via = outcome.schema_validated_via

            if schema_validated_via is None:
                mode = (
                    composed.validation_mode
                    if composed is not None and composed.validation_mode is not None
                    else "strict"
                )
                if mode == "off":
                    schema_validated_via = "off"

            # Reclassify expected, agent-level failures (rate-limit /
            # connection / auth / validation) from ``error`` → ``failed``.
            if not final_ok and final_status is None:
                final_status = classify_terminal_error(final_error)

            # ALWAYS emit the terminal DoneEvent through the session so
            # it lands last in both the transcript and WS stream.
            if not session.done_emitted:
                session.emit_done(
                    ok=bool(final_ok),
                    error=final_error,
                    status=final_status,
                )

        return StepResult(
            final_ok=final_ok,
            final_error=final_error,
            final_status=final_status,
            output=output,
            validation_status=validation_status,
            validation_errors=validation_errors,
            schema_validated_via=schema_validated_via,
            session=session,
        )


__all__ = ["RunStepLoop", "StepResult", "classify_terminal_error"]
