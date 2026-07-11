"""Pre-run setup: workdir, backend selection, render, MCP injection."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from agentbox.core.agents import resolve_engine
from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.data import RenderedConfig, RuntimeConfigView
from agentbox.core.data import ComposedReferenceView, ComposedView, PythonAgentConfigView
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.execution.orchestrate.generator import (
    _read_agent_config_json,
)
from agentbox.core.data import CanonicalTool
from agentbox.core.workspaces import resolve_path
from agentbox.core.workspaces.tooling.mcp.registry import McpRegistry
from agentbox.core.workspaces.tooling.catalog import resolve_workspace_callables

logger = logging.getLogger(__name__)


def _composed_view(composed: Any | None) -> ComposedView | None:
    if composed is None:
        return None
    references = tuple(
        ComposedReferenceView(path=r.path, heading=r.heading, content=r.content)
        for r in (getattr(composed, "references", None) or ())
    )
    return ComposedView(
        system=getattr(composed, "system", None),
        system_base=getattr(composed, "system_base", None),
        schema=getattr(composed, "schema", None),
        input_schema=getattr(composed, "input_schema", None),
        user=getattr(composed, "user", None),
        references=references,
        bundle_sha=getattr(composed, "bundle_sha", None),
        validation_mode=getattr(composed, "validation_mode", None),
    )


class NoBackendAvailable(RuntimeError):
    """Raised when ``select_backend`` cannot pick any adapter."""

    def __init__(self, *, agent_id: str, attempted: list[str]) -> None:
        self.agent_id = agent_id
        self.attempted = list(attempted)
        super().__init__(
            f"no backend available for agent {agent_id!r} (attempted: {self.attempted})"
        )


class RunSetup:
    """Pre-stream setup: workdir allocation, backend selection, render materialization."""

    def __init__(
        self,
        db: Any,
        settings: Settings,
        mcp_registry: "McpRegistry | None",
    ) -> None:
        self._db = db
        self.settings = settings
        self._mcp_registry = mcp_registry

    # ------------------------------------------------------------------ workdir
    def prepare_workdir(
        self,
        agent: AgentDef,
        session_id: str | None,
        workspace_override: str | None = None,
    ) -> tuple[Path, str | None]:
        ws_lookup = self._db.workspaces

        if workspace_override:
            original = agent.workspace
            agent.workspace = workspace_override
            try:
                path, ephemeral = resolve_path(agent, self.settings, ws_lookup)
            finally:
                agent.workspace = original
            if not ephemeral:
                path.mkdir(parents=True, exist_ok=True)
                return path, session_id

        path, ephemeral = resolve_path(agent, self.settings, ws_lookup)
        if not ephemeral:
            path.mkdir(parents=True, exist_ok=True)
            return path, session_id
        if agent.session_mode == "persistent":
            if session_id:
                existing = self._db.sessions.get_dict(session_id)
                if existing and existing["workdir"]:
                    self._db.sessions.touch(session_id)
                    return Path(existing["workdir"]), session_id
            self.settings.sessions_dir.mkdir(parents=True, exist_ok=True)
            sid = self._db.sessions.create_session(agent.id, agent.session_mode, None)
            wd = self.settings.sessions_dir / sid / "workdir"
            wd.mkdir(parents=True, exist_ok=True)
            self._db.sessions.set_workdir(sid, str(wd))
            return wd, sid
        self.settings.runs_dir.mkdir(parents=True, exist_ok=True)
        wd = (
            Path(tempfile.mkdtemp(prefix="run-", dir=self.settings.runs_dir))
            / "workdir"
        )
        wd.mkdir(parents=True, exist_ok=True)
        return wd, None

    # ------------------------------------------------------------------ backend
    def select_backend(
        self,
        agent: AgentDef,
        workdir: Path,
        backend_override: str | None = None,
        runner_config: EffectiveRunnerConfig | None = None,
        composed: Any | None = None,
    ) -> tuple["BackendAdapter", RenderedConfig]:
        # Resolve cross-domain values before render so backends don't
        # import from agents / workspaces / resources domains directly.
        agent_config_json = _read_agent_config_json(agent)
        runtime_config_view = RuntimeConfigView(
            allowed_tools=tuple(
                agent_config_json.get("runtime", {}).get("allowed_tools") or ()
            ),
            forbidden_tools=tuple(
                agent_config_json.get("runtime", {}).get("forbidden_tools") or ()
            ),
        )
        python_config_raw = agent_config_json.get("python", {}) or {}
        python_agent_config_view = PythonAgentConfigView(
            agent_module=python_config_raw.get("agent_module"),
            output_schema_path=python_config_raw.get("output_schema_path"),
        )

        ws_id = agent.workspace

        def _try_backend(name: str) -> "BackendAdapter | None":
            try:
                return resolve_engine(name)
            except KeyError:
                return None

        candidates: list[str] = []
        if backend_override:
            candidates = [backend_override]
        elif runner_config is not None and runner_config.backend:
            candidates = [runner_config.backend]

        for name in candidates:
            adapter = _try_backend(name)
            if adapter is None:
                continue
            # Availability surface for the agent ∩ workspace intersection —
            # computed per-backend so the engine's native declared_tools are
            # folded into what the workspace makes available.
            ws_callables = (
                resolve_workspace_callables(
                    ws_id,
                    self._db.workspace_file_resource_bindings,
                    self._db.workspace_mcp_policies,
                    self._db.workspace_mcp_overrides,
                    self._db.workspace_mcp_tool_overrides,
                    self._mcp_registry,
                    declared_tools=adapter.declared_tools(),
                )
                if ws_id
                else []
            )
            ws_allowed_tools: set[CanonicalTool] = set()
            for item in ws_callables:
                try:
                    ws_allowed_tools.add(CanonicalTool(item.name))
                except ValueError:
                    pass  # non-canonical (MCP, resources) aren't intersected
            rendered = adapter.render(
                agent,
                workdir,
                runner_config=runner_config,
                composed=_composed_view(composed),
                runtime_config=runtime_config_view,
                python_agent_config=python_agent_config_view,
                ws_allowed_tools=ws_allowed_tools,
            )
            return adapter, rendered

        raise NoBackendAvailable(agent_id=agent.id, attempted=candidates)

    # ------------------------------------------------------------------ MCP grants
    def resolve_agent_tool_grants(self, agent_id: str) -> set[str] | None:
        try:
            # list_for_agent(include_revoked=False) already excludes revoked rows
            grants = self._db.agent_tool_grants.list_for_agent(agent_id)
            grants_set = {g["tool_name"] for g in grants}
            if grants_set:
                return grants_set
        except Exception:
            logger.exception(
                "executor: agent-tools grant resolution failed for agent %r",
                agent_id,
            )
        return None

# fail_pre_run re-exported for backward compatibility.
from agentbox.core.execution.orchestrate.init_run import fail_pre_run  # noqa: F401, E402

__all__ = [
    "NoBackendAvailable",
    "RunSetup",
    "fail_pre_run",
]
