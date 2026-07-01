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
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.config import SETTINGS, Settings
from agentbox.core.data import AgentDef, RunRecord

from agentbox.core.execution.dispatch import dispatch_completion
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster

if TYPE_CHECKING:
    from agentbox.core.execution.orchestrate.steploop import StepResult

logger = logging.getLogger(__name__)


def cleanup_run_dir(run_dir: Path | None) -> None:
    """Remove the per-run scratch dir unless ``AGENTBOX_KEEP_RUN_DIRS=1``."""
    if run_dir is None:
        return
    if SETTINGS.keep_run_dirs:
        return
    shutil.rmtree(run_dir, ignore_errors=True)


def cleanup_workdir(agent: AgentDef, workdir: Path) -> None:
    """Remove an ephemeral, non-persistent workdir after the run ends."""
    if agent.workspace != "<ephemeral>":
        return
    if agent.session_mode == "persistent":
        return
    with contextlib.suppress(OSError):
        shutil.rmtree(workdir.parent, ignore_errors=True)


class _RunDispatchAdapter:
    """Minimal DispatchStore adapter backed by Database managers."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def get_run(self, run_id: str) -> Any:
        return self._db.runs.get(run_id)

    def set_run_status(self, run_id: str, status: str) -> None:
        self._db.runs.set_status(run_id, status)

    def get_usage(self, run_id: str) -> dict | None:
        return self._db.usage.get_dict(run_id)

    def record_webhook_delivery(
        self,
        run_id: str,
        attempt: int,
        url: str,
        payload: dict | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        self._db.webhook_deliveries.record(
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

    def __init__(self, db: Any, settings: Settings) -> None:
        self._db = db
        self.settings = settings

    def finalize(
        self,
        *,
        run_id: str,
        agent: AgentDef,
        adapter,
        transcript_path: Path,
        broadcaster: RunBroadcaster,
        workdir: Path,
        run_dir: Path,
        step_result: "StepResult | None",
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
                    self._db.runs.set_conversation(
                        run_id,
                        conversation_format=None,
                        conversation_uri=post_uri,
                    )
            except Exception:
                logger.exception(
                    "finalizer: failed to refresh conversation_uri for %s", run_id
                )

        if step_result is None:
            self._db.runs.finish_full(
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
            self._db.runs.finish_full(
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
            refreshed_run = self._db.runs.get(run_id)
            if refreshed_run is not None:
                _record_fields = {f.name for f in dataclasses.fields(RunRecord)}
                refreshed = RunRecord(**{
                    k: v for k, v in refreshed_run.model_dump().items()
                    if k in _record_fields
                })
                dispatch_completion(
                    run=refreshed,
                    agent=agent,
                    store=_RunDispatchAdapter(self._db),
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
            cleanup_workdir(agent, workdir)


__all__ = ["RunFinalizer", "cleanup_run_dir", "cleanup_workdir"]
