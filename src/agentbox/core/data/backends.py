"""Backend boundary shapes — the shared vocabulary of a backend run.

The canonical value types both the engines and execution/agents domains
exchange at the backend boundary: the immutable ``RenderedConfig`` a
backend ``render()`` produces, the ``BackendRunResult`` it reports, the
per-run ``RunRequest``, the MCP tool manifest ``McpToolSpec``, and the
engine-local *views* of agent config (``RuntimeConfigView``,
``PythonAgentConfigView``, ``ComposedView``, ``ComposedReferenceView``).

They live in ``core.data`` (the shapes leaf) so neither domain has to
reach across into the other to name them.
"""

from __future__ import annotations

from agentbox.core.data.jsontypes import RawJson

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from agentbox.core.data.manifests.agents import AgentDef
from agentbox.core.data.payload_types import AgentMetaDict
from agentbox.core.data.skills import SkillPack
from agentbox.core.data.tools import CanonicalTool


class McpToolSpec(TypedDict, total=False):
    name: str
    description: str
    # KEEP: JSON Schema document, structure varies.
    inputSchema: RawJson


# ── Engine-local views of agent config ───────────────────────────────────────


@dataclass(frozen=True)
class RuntimeConfigView:
    """Engine-local view of agent runtime config (``allowed_tools`` +
    ``forbidden_tools``).

    This is the only slice of ``core.agents.definition.RuntimeConfig`` that
    backends consume.
    """

    allowed_tools: tuple[CanonicalTool, ...] = ()
    forbidden_tools: tuple[CanonicalTool, ...] = ()


@dataclass(frozen=True)
class PythonAgentConfigView:
    """Engine-local view of agent python config (``agent_module``, schema path).

    This is the only slice of ``core.agents.definition.PythonAgentConfig``
    that backends consume.
    """

    agent_module: str | None = None
    output_schema_path: str | None = None


@dataclass(frozen=True)
class ComposedReferenceView:
    """Engine-local view of a composed prompt reference section.

    Mirrors ``core.agents.composition.bundle.compose.ComposedReference``.
    """

    path: str
    heading: str
    content: str


@dataclass(frozen=True)
class ComposedView:
    """Engine-local view of composed prompt state.

    Execution builds this from its richer ComposedState at the render
    boundary.
    """

    system: str | None = None
    system_base: str | None = None
    # KEEP: JSON Schema document, structure varies.
    schema: RawJson | None = None
    # KEEP: JSON Schema document, structure varies.
    input_schema: RawJson | None = None
    user: str | None = None
    references: tuple[ComposedReferenceView, ...] = ()
    bundle_sha: str | None = None
    validation_mode: str | None = None


# ── Run request / result ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BackendRunResult:
    """Terminal status reported by a backend after a run completes.

    Backends report their *runner-level* outcome here — did the
    subprocess exit cleanly, was there a runtime error, what was the
    exit code. Validation outcome is the executor's concern: it runs
    schema checks after the execution-layer pump returns and adjusts the
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
    agent: AgentDef
    input: str
    workdir: Path
    project_root: Path
    session_id: str | None = None
    runner_profile: str | None = None
    runner_config: dict[str, Any] | None = None


# ── Rendered config ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RenderedConfig:
    """Immutable description of an agent run's runtime configuration.

    ``render()`` on a backend adapter produces one of these. The executor
    passes the same object to ``run()`` so the adapter never needs to
    re-inspect the workspace.

    Cross-domain values that backends previously fetched via direct
    imports from ``core.agents.*``, ``core.workspace.*``, or
    ``core.resource.*`` are populated here by the executor during setup.
    Backends read them from this object — never from other domains.
    """

    argv: list[str] = field(default_factory=list)
    """Command + arguments to execute."""

    env: Mapping[str, str] = field(default_factory=dict)
    """Environment variable overrides for the subprocess."""

    cwd: Path = Path(".")
    """Working directory relative to the run workdir root."""

    agent_meta: AgentMetaDict = field(default_factory=AgentMetaDict)
    """Backend-specific agent metadata (e.g. agent_module, prompt for pydantic_ai
    in-process agents). Included in the digest computation."""

    model: str | None = None
    """Effective model name that will actually be used to run the agent.

    Set by the adapter during ``render()`` from EffectiveRunnerConfig or
    the backend's own default. Persisted by the executor so even runs
    that never emit a ``UsageEvent`` (timeouts, early crashes) keep a
    model name in the runs table.
    """

    digest: str = ""
    """sha256 over a sorted JSON serialisation of (argv, env, cwd, agent_meta).

    Computed automatically by ``compute_digest()``. Stable across identical
    inputs; changes when any tool, arg, or env var is added/removed.
    """

    # -- Cross-domain values populated by the executor ------------------------
    # These carry data from agents/workspaces/resources domains so backends
    # never import those domains directly.  The executor populates them in
    # ``core.execution.orchestrate.setup`` before calling ``adapter.render()``.

    mcp_tools: list[McpToolSpec] = field(default_factory=list)
    """MCP tool manifests resolved at run time."""

    host_env_server_cmd: list[str] = field(default_factory=list)
    """CLI args for the agentbox host-env MCP server."""

    agent_tools_server_cmd: list[str] = field(default_factory=list)
    """CLI args for the agentbox agent-tools MCP server."""

    runtime_config: RuntimeConfigView | None = None
    """Resolved runtime tooling config from the agent definition.

    Populated by the executor before ``render()`` so backends never
    import ``core.agents.definition`` directly."""

    python_agent_config: PythonAgentConfigView | None = None
    """Resolved python agent config from the agent definition.

    Populated by the executor before ``render()`` so backends never
    import ``core.agents.definition`` directly."""

    ws_allowed_tools: set[CanonicalTool] | None = None
    """Canonical tool names available in the workspace, pre-resolved via
    the workspace-tool catalog.

    Replaces the legacy ``host_capabilities`` dict.  Populated by the
    executor before ``render()`` so backends never import workspace or
    resource domains directly.  Backends feed this into
    ``intersect_allowed_tools`` as the workspace side of the
    agent ∩ workspace intersection."""

    host_capabilities: dict[str, Any] = field(default_factory=dict)
    """Deprecated: use ``ws_allowed_tools`` instead.

    Populated by the executor before ``render()`` so backends never
    import ``core.workspace.manager`` directly."""

    skill_packs: list[SkillPack] = field(default_factory=list)
    """Filtered skill packs for the workspace.

    Populated by the executor before ``render()`` so the render pipeline
    never imports ``core.resource.skills`` directly."""

    def __post_init__(self) -> None:
        if not self.digest:
            object.__setattr__(self, "digest", self.compute_digest())

    def compute_digest(self) -> str:
        canonical = json.dumps(
            {
                "argv": list(self.argv),
                "env": dict(self.env),
                "cwd": str(self.cwd),
                "agent_meta": dict(self.agent_meta),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()
