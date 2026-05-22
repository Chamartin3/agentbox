"""Pre-backend run preparation.

This package contains everything the executor does *before* selecting and
invoking a backend adapter: resource materialization, env-doc rendering,
subagent wiring, prompt composition, prompt-resource binding substitution,
and output-contract assembly.

Extracted from ``core/run/executor.py`` to keep the executor focused on its
core responsibility: backend selection, the event loop, validation retries,
and terminal bookkeeping.

Public API:

- :class:`PreparedResources` — typed result of pre-backend preparation.
- :func:`prepare_run_resources` — runs the pre-backend pipeline.
"""

from __future__ import annotations

from agentbox.core.run.prepare.resources import (
    PreparedResources,
    prepare_run_resources,
)

__all__ = ["PreparedResources", "prepare_run_resources"]
