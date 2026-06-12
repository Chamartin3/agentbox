"""Post-stream finalization for a run.

``RunFinalizer.finalize`` runs after the step loop completes (or
crashes). Its job is to:

* Re-persist ``conversation_uri`` for backends that discover their
  session ID mid-run (OpenCode).
* Call ``store.finish_run`` with the terminal status payload.
* Schedule the completion webhook.
* Close the broadcaster (drain WS subscribers).
* Tidy up the run scratch dir and the ephemeral workdir if applicable.

The finalizer never raises: a finalization failure is logged but the
run is still considered "done" — refusing to swallow exceptions here
would orphan WS subscribers and leave the row in ``running``.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.config import Settings
from agentbox.core.data import AgentDef, RunStore

from agentbox.core.execution.dispatch import dispatch_completion
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster

if TYPE_CHECKING:
    from agentbox.core.execution.orchestrate.steploop import StepResult

logger = logging.getLogger(__name__)


def cleanup_run_dir(run_dir: Path | None) -> None:
    """Remove the per-run scratch dir unless ``AGENTBOX_KEEP_RUN_DIRS=1``."""
    if run_dir is None:
        return
    if os.environ.get("AGENTBOX_KEEP_RUN_DIRS") == "1":
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


class RunFinalizer:
    """Persists terminal state, fires dispatch channels, and cleans up."""

    def __init__(self, store: RunStore, settings: Settings) -> None:
        self.store = store
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
        step_result: StepResult | None,
    ) -> None:
        """Terminal-state persist + webhook + cleanup.

        Mirrors the original ``finally`` block of ``RunExecutor._run``.
        ``step_result`` may be ``None`` if the step loop blew up before
        producing a result; in that case we still finish the run as a
        non-ok crash so the row never stays in ``running``.
        """
        # Re-persist conversation_uri for runners that discover their
        # session ID during execution (e.g. OpenCode).
        conv_meth = getattr(adapter, "conversation_uri", None)
        if conv_meth is not None:
            try:
                post_uri = conv_meth(
                    run_id=run_id, transcript_path=str(transcript_path)
                )
                if post_uri:
                    self.store.set_run_conversation(
                        run_id,
                        conversation_format=None,
                        conversation_uri=post_uri,
                    )
            except Exception:
                logger.exception(
                    "finalizer: failed to refresh conversation_uri for %s", run_id
                )

        # Preserve original behavior: when the step loop blows up
        # before producing a result, finish_run is called with the
        # zero-init defaults (ok=False, no output/error/status).
        if step_result is None:
            self.store.finish_run(
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
            self.store.finish_run(
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
            refreshed = self.store.get_run(run_id)
            if refreshed is not None:
                dispatch_completion(
                    run=refreshed,
                    agent=agent,
                    store=self.store,
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
