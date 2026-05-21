"""Central event-capture object for a single agent run.

Every ``RunEvent`` produced during a run flows through one
``RunStreamSession.emit()`` call. The session routes the event to three
sinks atomically — JSONL transcript on disk, in-memory broadcaster for
live WS subscribers, and an ``output_text`` accumulator for assistant
text — plus user-registered observers (e.g. usage recording).

The session also enforces two invariants that used to be implicit:

1. **DoneEvent must be the last event emitted.** Prior to this, the
   backend's terminal ``DoneEvent`` reached WS clients *before*
   post-run ``ValidationEvent`` / ``RetryEvent`` did, so UIs treating
   ``done`` as terminal lost the validation outcome. The executor now
   suppresses the backend's DoneEvent and calls ``emit_done()`` itself
   after validation has run.
2. **Single emission point.** Replaces the three-line
   ``_handle_event + broadcaster.publish + tf.write`` ritual scattered
   across the executor. If a future event type needs new side-effect
   handling, there's exactly one place to add it.

Tests use ``CaptureSession`` which drops the broadcaster + file and
keeps emitted events in a list.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, TextIO

from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RetryEvent,
    RunEvent,
    TextEvent,
    TimeoutEvent,
    ValidationEvent,
)

if TYPE_CHECKING:
    from agentbox.core.run.executor import RunBroadcaster

logger = logging.getLogger(__name__)

_VALIDATION_MODES = ("strict", "warn", "off")
_VALIDATION_ENGINES = ("jsonschema", "pydantic", "both", "none")


class DoneAlreadyEmittedError(RuntimeError):
    """Raised when ``emit()`` is called after a ``DoneEvent`` was emitted.

    Indicates a backend or executor bug — once the terminal event has
    gone out to WS clients, nothing else can follow.
    """


@dataclass
class RunStreamSession:
    """Single fan-out point for one run's event stream.

    Use as a context manager so the transcript file is closed even on
    error. ``__exit__`` does NOT emit a DoneEvent — the caller is
    responsible for emitting exactly one. (We considered auto-emitting
    on exit, but it hides bugs: a run that exits without explicit
    ``emit_done`` is almost always a logic error.)
    """

    run_id: str
    broadcaster: RunBroadcaster
    transcript_path: Path
    output_text: list[str] = field(default_factory=list)
    _transcript_fh: TextIO | None = None
    _done_emitted: bool = False
    _observers: list[Callable[[RunEvent], None]] = field(default_factory=list)

    # ----- lifecycle -------------------------------------------------------

    def __enter__(self) -> RunStreamSession:
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        # Line-buffered so partially-written runs are still readable from
        # disk if the process is killed mid-flight.
        self._transcript_fh = self.transcript_path.open(
            "a", encoding="utf-8", buffering=1
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        fh = self._transcript_fh
        self._transcript_fh = None
        if fh is not None:
            fh.close()

    # ----- registration ----------------------------------------------------

    def add_observer(self, fn: Callable[[RunEvent], None]) -> None:
        """Register a side-effect callback fired after every emit.

        Used by the executor to wire ``UsageEvent`` → ``store.record_usage``.
        Observer exceptions are logged and swallowed so a broken observer
        cannot drop events from the transcript or WS.
        """
        self._observers.append(fn)

    @property
    def done_emitted(self) -> bool:
        return self._done_emitted

    # ----- emission --------------------------------------------------------

    def emit(self, ev: RunEvent) -> None:
        """Route ``ev`` to transcript, broadcaster, accumulator, observers.

        Raises ``DoneAlreadyEmittedError`` if called after a ``DoneEvent``.
        """
        if self._done_emitted:
            raise DoneAlreadyEmittedError(
                f"event {type(ev).__name__} emitted after DoneEvent for "
                f"run {self.run_id} — DoneEvent must be terminal"
            )

        if self._transcript_fh is not None:
            self._transcript_fh.write(ev.model_dump_json() + "\n")

        self.broadcaster.publish(ev)

        # Delta events are UI-only; prompt turns get persisted+broadcast
        # but only consolidated assistant text becomes the run output.
        if isinstance(ev, TextEvent) and not ev.delta and ev.role == "assistant":
            self.output_text.append(ev.text)

        for fn in self._observers:
            try:
                fn(ev)
            except Exception:
                logger.exception(
                    "observer raised on %s event in run %s",
                    type(ev).__name__,
                    self.run_id,
                )

        if isinstance(ev, DoneEvent):
            # Set AFTER successful publish so a transcript write failure
            # doesn't lock us out of retrying.
            self._done_emitted = True

    # ----- convenience emitters -------------------------------------------
    #
    # Build the event with run_id pre-filled and apply the discriminator
    # validation that used to live inline in the executor. Keeps callers
    # from accidentally constructing events with unknown mode/engine
    # strings that fail Pydantic validation at write time.

    def emit_validation(
        self,
        *,
        ok: bool,
        mode: str,
        engine: str,
        error: str | None,
        attempt: int = 1,
    ) -> None:
        self.emit(
            ValidationEvent(
                run_id=self.run_id,
                ok=ok,
                attempt=attempt,
                mode=mode if mode in _VALIDATION_MODES else "strict",
                engine=engine if engine in _VALIDATION_ENGINES else "none",
                error=error,
            )
        )

    def emit_log(self, *, level: str, message: str) -> None:
        self.emit(LogEvent(run_id=self.run_id, level=level, message=message))

    def emit_retry(
        self, *, attempt: int, reason: str, error: str | None = None
    ) -> None:
        self.emit(
            RetryEvent(run_id=self.run_id, attempt=attempt, reason=reason, error=error)
        )

    def emit_timeout(self, *, timeout_seconds: int, error: str | None) -> None:
        self.emit(
            TimeoutEvent(
                run_id=self.run_id,
                timeout_seconds=timeout_seconds,
                error=error,
            )
        )

    def emit_done(
        self,
        *,
        ok: bool,
        exit_code: int | None = None,
        error: str | None = None,
        status: str | None = None,
    ) -> None:
        """Emit the terminal ``DoneEvent``. Must be called exactly once.

        After this, further ``emit()`` calls raise
        :class:`DoneAlreadyEmittedError`.
        """
        self.emit(
            DoneEvent(
                run_id=self.run_id,
                ok=ok,
                exit_code=exit_code,
                error=error,
                status=status,
            )
        )


class CaptureSession(RunStreamSession):
    """In-memory ``RunStreamSession`` for tests.

    Skips the transcript file and uses a no-op broadcaster. The list of
    emitted events is available as ``captured`` for assertions.
    """

    def __init__(self, run_id: str = "test-run") -> None:
        from agentbox.core.run.executor import RunBroadcaster

        super().__init__(
            run_id=run_id,
            broadcaster=RunBroadcaster(),
            transcript_path=Path("/dev/null"),
        )
        self.captured: list[RunEvent] = []

    def __enter__(self) -> CaptureSession:  # type: ignore[override]
        # Skip the file open — captures live in memory only.
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def emit(self, ev: RunEvent) -> None:  # type: ignore[override]
        if self._done_emitted:
            raise DoneAlreadyEmittedError(
                f"event {type(ev).__name__} emitted after DoneEvent for "
                f"run {self.run_id}"
            )
        self.captured.append(ev)
        # Accumulator + observer behavior must match production.
        if isinstance(ev, TextEvent) and not ev.delta and ev.role == "assistant":
            self.output_text.append(ev.text)
        for fn in self._observers:
            try:
                fn(ev)
            except Exception:
                logger.exception(
                    "observer raised on %s event in run %s",
                    type(ev).__name__,
                    self.run_id,
                )
        if isinstance(ev, DoneEvent):
            self._done_emitted = True
