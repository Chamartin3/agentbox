"""Tests for in-memory event pub/sub via RunBroadcaster."""

from __future__ import annotations


from agentbox.core.events import TextEvent
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster


class TestRunBroadcaster:
    def test_subscribe_receives_history(self) -> None:
        b = RunBroadcaster()
        ev = TextEvent(run_id="r1", text="hello")
        b.publish(ev)

        q = b.subscribe()
        history = q.get_nowait()
        assert history.text == "hello"

    def test_subscribe_after_close_receives_none(self) -> None:
        b = RunBroadcaster()
        b.close()

        q = b.subscribe()
        sentinel = q.get_nowait()
        assert sentinel is None

    def test_publish_fans_out_to_all_subscribers(self) -> None:
        b = RunBroadcaster()
        q1 = b.subscribe()
        q2 = b.subscribe()

        ev = TextEvent(run_id="r1", text="fanout")
        b.publish(ev)

        assert q1.get_nowait().text == "fanout"
        assert q2.get_nowait().text == "fanout"

    def test_close_sends_none_and_clears_subscribers(self) -> None:
        b = RunBroadcaster()
        q1 = b.subscribe()
        q2 = b.subscribe()
        b.publish(TextEvent(run_id="r1", text="before close"))

        b.close()

        assert q1.get_nowait().text == "before close"
        assert q1.get_nowait() is None
        assert q2.get_nowait().text == "before close"
        assert q2.get_nowait() is None

    def test_subscribe_replays_history_then_live(self) -> None:
        b = RunBroadcaster()
        b.publish(TextEvent(run_id="r1", text="past"))
        q = b.subscribe()

        assert q.get_nowait().text == "past"

        b.publish(TextEvent(run_id="r1", text="live"))
        assert q.get_nowait().text == "live"

    def test_multiple_events_in_history(self) -> None:
        b = RunBroadcaster()
        b.publish(TextEvent(run_id="r1", text="first"))
        b.publish(TextEvent(run_id="r1", text="second"))

        q = b.subscribe()
        assert q.get_nowait().text == "first"
        assert q.get_nowait().text == "second"
