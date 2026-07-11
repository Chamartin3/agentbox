"""Per-run retry + validation orchestrator.

Owns the loop body that used to live inline at ``executor._run`` between
``with session:`` and the terminal bookkeeping (~240 lines). The executor
remains responsible for everything around the loop: session
construction, observers, deadline computation, terminal
status reclassification, ``finish_run``.

The loop's responsibility:
1. Honour the shared wall-clock deadline (the executor passes it in).
2. Invoke the backend with that deadline.
3. Recover output (possibly from ``output.json``) when a schema is set.
4. On runner failure → consume an *error* retry, rebuild prompt, retry.
5. On schema failure → consume a *validation* retry, rebuild prompt,
   retry. Final-attempt failure with ``mode == "strict"`` flips the
   final status to ``FAILED``.
6. Success path → return.

Single value returned: :class:`RetryOutcome`. The executor unpacks it
and continues with bookkeeping.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback as _tb
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox.core.agents import check_output
from agentbox.core.data._util import extract_json
from agentbox.core.data.constants import LogLevel
from agentbox.core.data.events import DoneEvent
from agentbox.core.data.constants import RunStatus
from agentbox.core.data.composition import ComposedPrompt
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.data import RenderedConfig
from agentbox.core.data import BackendRunResult
from agentbox.core.execution.observability.stream import RunStreamSession

logger = logging.getLogger(__name__)


@dataclass
class RetryOutcome:
    """Terminal state of the retry loop.

    The executor reads these fields and continues with
    ``finish_run``. ``final_status`` may still be ``None`` for the
    success path — the executor reclassifies expected-failure error
    strings after the fact.
    """

    final_ok: bool
    final_error: str | None
    final_status: str | None
    output: str | None
    validation_status: str | None
    validation_errors: list[str] | None
    schema_validated_via: str | None


def build_retry_prompt(
    original_input: str, previous_output: str, validation_error: str
) -> str:
    return (
        f"{original_input}\n\n"
        f"--- PREVIOUS ATTEMPT FAILED VALIDATION ---\n"
        f"Your previous output did not pass validation:\n\n"
        f"{validation_error}\n\n"
        f"--- YOUR PREVIOUS OUTPUT ---\n"
        f"{previous_output}\n\n"
        f"--- FIX IT ---\n"
        f"Fix the issues above and produce a corrected output that passes validation."
    )


def build_error_retry_prompt(
    original_input: str, previous_output: str | None, error: str | None
) -> str:
    parts = [
        f"{original_input}\n\n",
        "--- PREVIOUS ATTEMPT FAILED ---\n",
    ]
    if error:
        parts.append(f"The run failed with the following error:\n\n{error}\n\n")
    if previous_output:
        parts.append(f"--- YOUR PREVIOUS OUTPUT ---\n{previous_output}\n\n")
    parts.append(
        "--- FIX IT ---\n"
        "Review the error above, correct the issue, and produce a new output."
    )
    return "".join(parts)


def maybe_load_output_file(current: str | None, workdir: Path) -> str | None:
    """Return ``workdir/output.json`` content when ``current`` isn't JSON.

    Agents occasionally write structured output to disk instead of
    inlining it. If the runner's text output doesn't parse as JSON and
    an ``output.json`` file exists in the workdir, swap it in so
    validation can engage on the file content. Falls back to ``current``
    on any IO/decode failure.
    """
    if current:
        try:
            json.loads(extract_json(current))
            return current
        except (json.JSONDecodeError, ValueError):
            pass
    candidate = workdir / "output.json"
    try:
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8").strip()
            if content:
                return content
    except OSError:
        pass
    return current


async def pump_into_session(
    adapter: Any,
    rendered: RenderedConfig,
    input_: str,
    session: RunStreamSession,
) -> BackendRunResult:
    """Pump backend events into ``session`` and return terminal status."""
    direct = getattr(adapter, "run_into_session", None)
    if direct is not None:
        return await direct(rendered, input_, session)

    result = BackendRunResult(ok=False)
    async for ev in adapter.run(rendered, input_, session.run_id):
        if isinstance(ev, DoneEvent):
            result = BackendRunResult(
                ok=ev.ok,
                exit_code=ev.exit_code,
                error=ev.error,
                status=ev.status,
            )
            continue
        session.emit(ev)
    return result


class RetryOrchestrator:
    """Drives the per-run retry+validation loop.

    One instance per run. Holds the static refs the loop needs;
    :meth:`execute` runs the loop with the per-run config.
    """

    def __init__(
        self,
        *,
        adapter: BackendAdapter,
        rendered: RenderedConfig,
        agent: Any,
        composed: ComposedPrompt | None,
        workdir: Path,
        project_root: Path,
    ) -> None:
        self.adapter = adapter
        self.rendered = rendered
        self.agent = agent
        self.composed = composed
        self.workdir = workdir
        self.project_root = project_root

    async def execute(
        self,
        *,
        initial_input: str,
        max_attempts: int,
        error_retries_left: int,
        validation_retries_left: int,
        timeout_seconds: int,
        deadline: float,
        has_schema: bool,
        validation_mode: str,
        session: RunStreamSession,
    ) -> RetryOutcome:
        current_input = initial_input
        final_ok = False
        final_error: str | None = None
        final_status: str | None = None
        output: str | None = None
        validation_status: str | None = None
        validation_errors: list[str] | None = None
        schema_validated_via: str | None = None

        for attempt in range(max_attempts):
            session.output_text.clear()
            run_error: str | None = None

            # Shared wall-clock deadline check.
            if asyncio.get_event_loop().time() >= deadline:
                run_error = (
                    f"timeout after {timeout_seconds}s "
                    f"(budget exhausted across {attempt} attempt"
                    f"{'s' if attempt != 1 else ''})"
                )
                final_error = run_error
                final_ok = False
                final_status = RunStatus.TIMEOUT.value
                session.emit_timeout(timeout_seconds=timeout_seconds, error=run_error)
                session.emit_log(level=LogLevel.ERROR, message=run_error)
                break

            try:
                async with asyncio.timeout_at(deadline):
                    backend_result = await pump_into_session(
                        self.adapter, self.rendered, current_input, session
                    )
                    final_ok = backend_result.ok
                    final_error = backend_result.error
                    final_status = backend_result.status
            except TimeoutError:
                run_error = f"timeout after {timeout_seconds}s"
                final_error = run_error
                final_ok = False
                final_status = RunStatus.TIMEOUT.value
                if timeout_seconds is not None:
                    session.emit_timeout(
                        timeout_seconds=timeout_seconds, error=run_error
                    )
            except Exception as exc:
                tb_text = _tb.format_exc()
                run_error = (
                    f"executor error: {type(exc).__name__}: {exc}\n{tb_text}"
                )
                final_error = run_error
                final_ok = False
                logger.exception("runner crashed for run %s", session.run_id)

            if run_error:
                session.emit_log(level=LogLevel.ERROR, message=run_error)

            output = "\n".join(session.output_text).strip() or None

            if has_schema:
                output = maybe_load_output_file(output, self.workdir)

            # --- Error recovery (any failure including timeout) ---
            if not final_ok:
                if error_retries_left > 0:
                    error_retries_left -= 1
                    reason = (
                        "timeout"
                        if final_status == RunStatus.TIMEOUT.value
                        else "run_error"
                    )
                    current_input = build_error_retry_prompt(
                        initial_input, output, final_error
                    )
                    session.emit_retry(
                        attempt=attempt + 1,
                        reason=reason,
                        error=final_error,
                    )
                    session.emit_log(
                        level=LogLevel.WARN,
                        message=(
                            f"Run failed (attempt {attempt + 1}): "
                            f"{final_error} — retrying "
                            f"({error_retries_left} left)"
                        ),
                    )
                    continue
                break

            # --- Validation retry (output schema check) -----------
            if has_schema and validation_mode != "off":
                result = check_output(
                    self.agent,
                    self.workdir,
                    output,
                    project_root=self.project_root,
                    composed=self.composed,
                )
                schema_validated_via = result.engine
                session.emit_validation(
                    ok=result.ok,
                    attempt=attempt + 1,
                    mode=validation_mode,
                    engine=result.engine,
                    error=None if result.ok else result.error,
                )
                if result.ok:
                    validation_status = "ok"
                    validation_errors = None
                    break
                validation_status = "fail"
                validation_errors = [result.error]
                if validation_retries_left > 0:
                    validation_retries_left -= 1
                    current_input = build_retry_prompt(
                        initial_input, output or "", result.error
                    )
                    session.emit_retry(
                        attempt=attempt + 1,
                        reason="validation_failed",
                        error=result.error,
                    )
                    session.emit_log(
                        level=LogLevel.WARN,
                        message=(
                            f"Validation failed (attempt {attempt + 1}): "
                            f"{result.error} — retrying "
                            f"({validation_retries_left} left)"
                        ),
                    )
                    continue
                if validation_mode == "strict":
                    final_ok = False
                    final_error = f"output validation failed: {result.error}"
                    final_status = RunStatus.FAILED.value
                elif validation_mode == "warn":
                    validation_status = "warn"
                break

            # Success path — no validation configured or passed.
            break

        return RetryOutcome(
            final_ok=final_ok,
            final_error=final_error,
            final_status=final_status,
            output=output,
            validation_status=validation_status,
            validation_errors=validation_errors,
            schema_validated_via=schema_validated_via,
        )
