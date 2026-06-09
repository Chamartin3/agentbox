"""Per-run dataclasses consumed by backends and executor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._mcp_types import McpToolSpec  # noqa: F401  # re-export
from .views import PythonAgentConfigView, RuntimeConfigView


@dataclass(frozen=True)
class PostRenderContext:
    """Inputs to :meth:`BackendAdapter.post_render`.

    The executor resolves grants and run paths before the hook runs;
    backends just do file mutations (or skip). ``host_env_grants`` /
    ``agent_tool_grants`` are ``None`` when there's nothing to inject —
    the default :meth:`BackendAdapter.post_render` checks for this.
    """

    run_dir: Path
    workdir: Path
    db_path: Path
    workspace_id: str | None
    agent_id: str
    host_env_grants: dict[str, Any] | None = None
    agent_tool_grants: set[str] | None = None


@dataclass(frozen=True)
class BackendRunResult:
    """Terminal status reported by a backend after a run completes.

    Backends report their *runner-level* outcome here — did the
    subprocess exit cleanly, was there a runtime error, what was the
    exit code. Validation outcome is the executor's concern: it runs
    schema checks AFTER ``run_into_session`` returns and adjusts the
    final state accordingly before emitting the terminal ``DoneEvent``.

    Why a return value instead of a streamed ``DoneEvent``: the executor
    must enforce "DoneEvent is the last event emitted" so WS clients
    see validation results before they treat the run as terminal.
    Returning the status keeps the backend out of the ordering decision.
    """

    ok: bool
    exit_code: int | None = None
    error: str | None = None
    status: str | None = None  # "ok" | "error" | "timeout" | None


@dataclass
class RunRequest:
    """Per-run inputs handed to a backend's ``run()`` (legacy shape, kept
    for direct in-process callers).

    Most code paths use :class:`RenderedConfig` instead — the executor
    renders once and then calls ``run(rendered, input, run_id)``. This
    dataclass survives for tests and the few helpers that still want a
    single object holding everything about a run.
    """

    run_id: str
    agent: Any  # AgentDef — avoids a circular import; runtime type is AgentDef.
    input: str
    workdir: Path
    project_root: Path
    session_id: str | None = None
    runner_profile: str | None = None
    runner_config: dict[str, Any] | None = None
