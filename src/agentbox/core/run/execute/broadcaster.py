"""In-memory pub/sub for a single run's event stream.

The broadcaster is the bridge between the executor (single producer)
and any number of WebSocket subscribers (multi consumer). It keeps a
short history so a late-joining subscriber catches up to the current
state of the run before tailing live events.

This is not really executor logic — it's a generic fan-out primitive —
so it lives in the ``execute`` subpackage as a leaf module.
"""

from __future__ import annotations

import asyncio

from agentbox.api.events import RunEvent


class RunBroadcaster:
    """In-memory pub/sub for one run's event stream."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[RunEvent | None]] = []
        self._history: list[RunEvent] = []
        self._closed = False

    def subscribe(self) -> asyncio.Queue[RunEvent | None]:
        q: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        for ev in self._history:
            q.put_nowait(ev)
        if self._closed:
            q.put_nowait(None)
        else:
            self._subscribers.append(q)
        return q

    def publish(self, ev: RunEvent) -> None:
        self._history.append(ev)
        for q in self._subscribers:
            q.put_nowait(ev)

    def close(self) -> None:
        self._closed = True
        for q in self._subscribers:
            q.put_nowait(None)
        self._subscribers.clear()


__all__ = ["RunBroadcaster"]
