"""Drive the backend stream and aggregate it into terminal state.

``RunStepLoop`` owns everything between "we have an adapter + rendered
config" and "the run is logically complete (terminal status known)".
It does *not* persist the terminal state — that's the finalizer's job.

The actual per-event work (transcript append, WS broadcast, usage
record, schema validation, retry-on-validation-failure) is handled by
:class:`agentbox.core.run.retry.RetryOrchestrator` and
:class:`agentbox.core.run.streaming.session.RunStreamSession`; the step
loop just wires those together and runs guardrails post-stream.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from agentbox.api.events import GuardrailEvent, UsageEvent
from agentbox.config import Settings
from agentbox.core.agent.plugins import get_guardrail
from agentbox.core.agent.profiles import EffectiveRunnerConfig
from agentbox.core.constants import RunStatus
from agentbox.core.data import AgentDef, SessionStore
from agentbox.core.run.backends.base import RenderedConfig
from agentbox.core.run.guardrails.base import GuardrailContext
from agentbox.core.run.retry import RetryOrchestrator
from agentbox.core.run.streaming.session import RunStreamSession

from agentbox.core.run.execute.broadcaster import RunBroadcaster

if TYPE_CHECKING:
    from agentbox.core.run.backends.base import BackendAdapter

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

    def __init__(self, store: SessionStore, settings: Settings) -> None:
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
        from agentbox.core.agent.config import ExecutionConfig, PythonAgentConfig
        from agentbox.core.agent.config import resolve_output_config as _resolve_oc

        exec_cfg = ExecutionConfig.from_agent(agent)
        python_cfg = PythonAgentConfig.from_agent(agent)

        error_retries_left = exec_cfg.max_error_retries or 0
        validation_retries_left = exec_cfg.max_validation_retries or 0
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
            _oc = _resolve_oc(self.store, agent)
            has_schema = bool(
                python_cfg.output_schema_path
                or (composed is not None and isinstance(composed.schema, dict))
                or _oc.json_schema is not None
                or bool(_oc.validators)
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

            try:
                await self._run_guardrails(
                    run_id, agent, input_, output or "", session
                )
            except Exception as exc:
                suffix = f"guardrail error: {exc}"
                final_error = f"{final_error} | {suffix}" if final_error else suffix

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

    async def _run_guardrails(
        self,
        run_id: str,
        agent: AgentDef,
        input_: str,
        output: str,
        session: RunStreamSession,
    ) -> None:
        for idx, ref in enumerate(agent.guardrails):
            try:
                cls = get_guardrail(ref.name)
            except KeyError as exc:
                session.emit(
                    GuardrailEvent(
                        run_id=run_id, name=ref.name, ok=False, message=str(exc)
                    )
                )
                continue
            instance = cls()
            ctx = GuardrailContext(
                run_id=run_id,
                agent_id=agent.id,
                input=input_,
                output=output,
                transcript_path=str(session.transcript_path),
                attempt=idx,
                options=ref.options,
            )
            result = instance.evaluate(ctx)
            self.store.record_guardrail(
                run_id, ref.name, result.ok, result.message, attempt=idx
            )
            session.emit(
                GuardrailEvent(
                    run_id=run_id,
                    name=ref.name,
                    ok=result.ok,
                    message=result.message,
                    attempt=idx,
                )
            )


__all__ = ["RunStepLoop", "StepResult", "classify_terminal_error"]
