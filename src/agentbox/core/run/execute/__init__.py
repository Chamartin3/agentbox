"""Run-execution collaborators.

This package holds the helpers that ``RunExecutor`` composes together
to drive a single agent run end-to-end. Each module owns one phase of
the run lifecycle (setup, step loop, finalization, webhook delivery,
snapshots, broadcasting) and stays under 400 LOC.

``RunExecutor`` in ``agentbox.core.run.executor`` remains the public
entry point — these collaborators are an implementation detail.
"""

from __future__ import annotations

from agentbox.core.run.execute.broadcaster import RunBroadcaster

__all__ = ["RunBroadcaster"]
