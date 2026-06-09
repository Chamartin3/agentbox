"""Pre-run setup: workdir, backend selection, render, MCP injection."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.agents.resolve import resolve_engine
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.data import AgentDef, RunSetupStore
from agentbox.config import Settings
from agentbox.core.engines.backends.base import (
    PostRenderContext,
    PythonAgentConfigView,
    RenderedConfig,
    RuntimeConfigView,
)
from agentbox.core.execution.orchestrate.generator import (
    _read_agent_config_json,
    make_generator,
)
from agentbox.core.execution.orchestrate.materialize import materialize_rendered_config
from agentbox.core.execution.orchestrate.permissions import load_workspace_permissions
from agentbox.core.workspaces import (
    load_capabilities,
    resolve_path,
)

if TYPE_CHECKING:
    from agentbox.core.engines.backends.base import BackendAdapter
    from agentbox.core.workspaces import McpRegistry

logger = logging.getLogger(__name__)


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
        store: RunSetupStore,
        settings: Settings,
        mcp_registry: McpRegistry | None,
    ) -> None:
        self.store = store
        self.settings = settings
        self._mcp_registry = mcp_registry

    # ------------------------------------------------------------------ workdir
    def prepare_workdir(
        self,
        agent: AgentDef,
        session_id: str | None,
        workspace_override: str | None = None,
    ) -> tuple[Path, str | None]:
        if workspace_override:
            original = agent.workspace
            agent.workspace = workspace_override
            try:
                path, ephemeral = resolve_path(agent, self.settings, self.store)  # type: ignore[arg-type]
            finally:
                agent.workspace = original
            if not ephemeral:
                path.mkdir(parents=True, exist_ok=True)
                return path, session_id

        path, ephemeral = resolve_path(agent, self.settings, self.store)  # type: ignore[arg-type]
        if not ephemeral:
            path.mkdir(parents=True, exist_ok=True)
            return path, session_id
        if agent.session_mode == "persistent":
            if session_id:
                existing = self.store.get_session(session_id)
                if existing and existing["workdir"]:
                    self.store.touch_session(session_id)
                    return Path(existing["workdir"]), session_id
            self.settings.sessions_dir.mkdir(parents=True, exist_ok=True)
            sid = self.store.create_session(agent.id, agent.session_mode, None)
            wd = self.settings.sessions_dir / sid / "workdir"
            wd.mkdir(parents=True, exist_ok=True)
            self.store.set_session_workdir(sid, str(wd))
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
    ) -> tuple[BackendAdapter, RenderedConfig]:
        # Resolve cross-domain values before render so backends don't
        # import from agents / workspaces / resources domains directly.
        agent_config_json = _read_agent_config_json(agent)
        runtime_config_view = RuntimeConfigView(
            allowed_tools=tuple(
                agent_config_json.get("runtime", {}).get("allowed_tools") or ()
            ),
        )
        python_config_raw = agent_config_json.get("python", {}) or {}
        python_agent_config_view = PythonAgentConfigView(
            agent_module=python_config_raw.get("agent_module"),
            output_schema_path=python_config_raw.get("output_schema_path"),
        )
        host_capabilities = load_capabilities(workdir)

        def _try_backend(name: str) -> BackendAdapter | None:
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
            if adapter is not None:
                rendered = adapter.render(
                    agent,
                    workdir,
                    runner_config=runner_config,
                    composed=composed,
                    runtime_config=runtime_config_view,
                    python_agent_config=python_agent_config_view,
                    host_capabilities=host_capabilities,
                )
                return adapter, rendered

        raise NoBackendAvailable(agent_id=agent.id, attempted=candidates)

    # ------------------------------------------------------------------ render
    def render_for_run(
        self,
        adapter: BackendAdapter,
        agent: AgentDef,
        workdir: Path,
        rendered: RenderedConfig,
    ) -> tuple[RenderedConfig, Path]:
        run_dir = self.settings.runs_tmpfs_dir / uuid.uuid4().hex
        materialize_rendered_config(rendered, run_dir)

        permissions = load_workspace_permissions(
            workdir, agent, self.settings, self.store
        )
        generator = make_generator(
            settings=self.settings, store=self.store, mcp_registry=self._mcp_registry
        )
        generator.generate_configs_into(
            run_dir,
            allowed_builtin_tools=permissions.get("allowed_builtin_tools") or [],
            files=permissions.get("files") or [],
            project_root=self.settings.project_root,
        )

        effective_cwd = rendered.cwd
        if not effective_cwd.is_absolute():
            effective_cwd = run_dir / effective_cwd

        return (
            RenderedConfig(
                files=rendered.files,
                argv=rendered.argv,
                env=rendered.env,
                cwd=effective_cwd,
                agent_meta=rendered.agent_meta,
                model=rendered.model,
            ),
            run_dir,
        )

    # ------------------------------------------------------------------ MCP grants
    def resolve_agent_tool_grants(self, agent_id: str) -> set[str] | None:
        try:
            grants_set = self.store.list_active_grants(agent_id)
            if grants_set:
                return grants_set
        except Exception:
            logger.exception(
                "executor: agent-tools grant resolution failed for agent %r",
                agent_id,
            )
        return None

    def post_render(
        self,
        adapter: BackendAdapter,
        rendered: RenderedConfig,
        *,
        run_dir: Path,
        workdir: Path,
        workspace_id: str | None,
        agent_id: str,
        host_env_grants: dict | None,
        agent_tool_grants: set[str] | None,
    ) -> None:
        try:
            adapter.post_render(
                rendered,
                PostRenderContext(
                    run_dir=run_dir,
                    workdir=workdir,
                    db_path=self.settings.db_path,
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    host_env_grants=host_env_grants,
                    agent_tool_grants=agent_tool_grants,
                ),
            )
        except Exception:
            logger.exception(
                "executor: post_render failed for agent %r",
                agent_id,
            )


# fail_pre_run re-exported from pre_run.py for backward compatibility.
from agentbox.core.execution.orchestrate.pre_run import fail_pre_run  # noqa: F401, E402

__all__ = [
    "NoBackendAvailable",
    "RunSetup",
    "fail_pre_run",
    "load_workspace_permissions",
]
