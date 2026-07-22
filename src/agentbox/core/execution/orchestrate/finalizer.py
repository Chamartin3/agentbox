"""Post-stream finalization for a run.

``RunFinalizer.finalize`` runs after the step loop completes (or
crashes). Its job is to:

* Re-persist ``conversation_uri`` for backends that discover their
  session ID mid-run (OpenCode).
* Call ``db.runs.finish_full`` with the terminal status payload.
* Schedule the completion webhook.
* Close the broadcaster (drain WS subscribers).
* Tidy up the run scratch dir and the ephemeral workdir if applicable.

The finalizer never raises: a finalization failure is logged but the
run is still considered "done" — refusing to swallow exceptions here
would orphan WS subscribers and leave the row in ``running``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
import shutil
from pathlib import Path
from typing import Any, cast

from agentbox.core.config import Settings
from agentbox.core.data import UsagePayload
from agentbox.core.data import AgentDef, RunRecord
from agentbox.core.db import RunManager, UsageManager, WebhookDeliveryManager
from agentbox.core.engines.backends import BackendAdapter
from agentbox.core.execution.dispatch import dispatch_completion
from agentbox.core.execution.observability.stream.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.steploop import StepResult

logger = logging.getLogger(__name__)


def cleanup_run_dir(run_dir: Path | None) -> None:
    """Remove the per-run scratch dir unless ``AGENTBOX_KEEP_RUN_DIRS=1``."""
    if run_dir is None:
        return
    # Debug knob (dev/local only, not a user setting): keep run dirs for inspection.
    if os.environ.get("AGENTBOX_KEEP_RUN_DIRS", "").lower() in {"1", "true", "yes"}:
        return
    shutil.rmtree(run_dir, ignore_errors=True)


def cleanup_workdir(workdir: Path, dispose: bool) -> None:
    """Remove the workdir when it is a throwaway (dispose=True)."""
    if not dispose:
        return
    with contextlib.suppress(OSError):
        shutil.rmtree(workdir.parent, ignore_errors=True)


class _RunDispatchAdapter:
    """Minimal DispatchStore adapter backed by specific managers."""

    def __init__(
        self,
        *,
        runs: RunManager,
        usage: UsageManager,
        webhook_deliveries: WebhookDeliveryManager,
    ) -> None:
        self._runs = runs
        self._usage = usage
        self._webhook_deliveries = webhook_deliveries

    def get_run(self, run_id: str) -> Any:
        return self._runs.get(run_id)

    def set_run_status(self, run_id: str, status: str) -> None:
        self._runs.set_status(run_id, status)

    def get_usage(self, run_id: str) -> UsagePayload | None:
        # UsageRow and UsagePayload are structurally equivalent at runtime;
        # cast bridges the minor TypedDict field variance difference.
        return cast(UsagePayload, row) if (row := self._usage.get_dict(run_id)) is not None else None

    def record_webhook_delivery(
        self,
        run_id: str,
        attempt: int,
        url: str,
        payload: dict[str, Any] | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        self._webhook_deliveries.record(
            run_id,
            attempt,
            url,
            payload=payload,
            response_status=response_status,
            response_body=response_body,
            latency_ms=latency_ms,
            error=error,
        )


class RunFinalizer:
    """Persists terminal state, fires dispatch channels, and cleans up."""

    def __init__(
        self,
        *,
        runs: RunManager,
        usage: UsageManager,
        webhook_deliveries: WebhookDeliveryManager,
        settings: Settings,
    ) -> None:
        self._runs = runs
        self._usage = usage
        self._webhook_deliveries = webhook_deliveries
        self.settings = settings

    def finalize(
        self,
        *,
        run_id: str,
        agent: AgentDef,
        adapter: BackendAdapter,
        transcript_path: Path,
        broadcaster: RunBroadcaster,
        workdir: Path,
        run_dir: Path,
        step_result: "StepResult | None",
        dispose_workdir: bool = False,
    ) -> None:
        """Terminal-state persist + webhook + cleanup."""
        # Re-persist conversation_uri for runners that discover their
        # session ID during execution (e.g. OpenCode).
        conv_meth = getattr(adapter, "conversation_uri", None)
        if conv_meth is not None:
            try:
                post_uri = conv_meth(
                    run_id=run_id, transcript_path=str(transcript_path)
                )
                if post_uri:
                    self._runs.set_conversation(
                        run_id,
                        conversation_format=None,
                        conversation_uri=post_uri,
                    )
            except Exception:
                logger.exception(
                    "finalizer: failed to refresh conversation_uri for %s", run_id
                )

        if step_result is None:
            self._runs.finish_full(
                run_id,
                ok=False,
                output=None,
                error=None,
                status=None,
                validation_status=None,
                validation_errors=None,
                schema_validated_via=None,
            )
        else:
            self._runs.finish_full(
                run_id,
                ok=step_result.final_ok,
                output=step_result.output,
                error=step_result.final_error,
                status=step_result.final_status,
                validation_status=step_result.validation_status,
                validation_errors=step_result.validation_errors,
                schema_validated_via=step_result.schema_validated_via,
            )

        try:
            refreshed_run = self._runs.get(run_id)
            if refreshed_run is not None:
                _record_fields = {f.name for f in dataclasses.fields(RunRecord)}
                refreshed = RunRecord(**{
                    k: v for k, v in refreshed_run.model_dump().items()
                    if k in _record_fields
                })
                dispatch_completion(
                    run=refreshed,
                    agent=agent,
                    store=_RunDispatchAdapter(
                        runs=self._runs,
                        usage=self._usage,
                        webhook_deliveries=self._webhook_deliveries,
                    ),
                    broadcaster=broadcaster,
                    transcript_path=transcript_path,
                    settings=self.settings,
                )
        except Exception:
            logger.exception("finalizer: dispatch failed for %s", run_id)

        with contextlib.suppress(Exception):
            broadcaster.close()
        with contextlib.suppress(Exception):
            cleanup_run_dir(run_dir)
        with contextlib.suppress(Exception):
            cleanup_workdir(workdir, dispose_workdir)


__all__ = ["RunFinalizer", "cleanup_run_dir", "cleanup_workdir"]
