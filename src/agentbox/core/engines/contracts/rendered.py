"""RenderedConfig — immutable run config dataclass."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentbox.core.resources.skills import SkillPack
from ._mcp_types import McpToolSpec
from .views import PythonAgentConfigView, RuntimeConfigView


@dataclass(frozen=True)
class RenderedConfig:
    """Immutable description of an agent run's runtime configuration.

    ``render()`` on a backend adapter produces one of these. The executor
    materialises ``files`` to disk, then passes the same object to
    ``run()`` so the adapter never needs to re-inspect the workspace.

    Cross-domain values that backends previously fetched via direct
    imports from ``core.agents.*``, ``core.workspace.*``, or
    ``core.resource.*`` are populated here by the executor during setup.
    Backends read them from this object — never from other domains.
    """

    files: Mapping[Path, bytes] = field(default_factory=dict)
    """Files to materialise inside the run workdir (relative paths)."""

    argv: list[str] = field(default_factory=list)
    """Command + arguments to execute."""

    env: Mapping[str, str] = field(default_factory=dict)
    """Environment variable overrides for the subprocess."""

    cwd: Path = Path(".")
    """Working directory relative to the run workdir root."""

    agent_meta: dict[str, Any] = field(default_factory=dict)
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
    """sha256 over a sorted JSON serialisation of (files, argv, env, cwd, agent_meta).

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
    import ``core.agents.config`` directly."""

    python_agent_config: PythonAgentConfigView | None = None
    """Resolved python agent config from the agent definition.

    Populated by the executor before ``render()`` so backends never
    import ``core.agents.config`` directly."""

    host_capabilities: dict[str, Any] = field(default_factory=dict)
    """Workspace host capabilities dict (allowed_tools, mcp_config_path, …).

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
                "files": {str(p): h.hex() for p, h in sorted(self.files.items())},
                "argv": list(self.argv),
                "env": dict(self.env),
                "cwd": str(self.cwd),
                "agent_meta": dict(self.agent_meta),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()
