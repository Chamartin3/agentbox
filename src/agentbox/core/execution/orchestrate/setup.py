"""Pre-run setup: workdir, backend selection, render, MCP injection.

This module owns the synchronous, pre-stream phase of a run:

* :class:`NoBackendAvailable` — raised when no adapter resolves.
* :func:`load_workspace_permissions` — DB overlay → permissions dict.
* :class:`RunSetup` — workdir resolution, backend pick, render-config
  materialization, generator config write, and per-backend MCP
  post-render hooks.
* :func:`fail_pre_run` — short-circuit terminal "couldn't even start"
  failure that creates the run row in error state and broadcasts a
  ``DoneEvent`` so any subscribed UI tears down cleanly.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.agents.resolve import resolve_engine
from agentbox.core.agents.config import RuntimeConfig
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.data import DoneEvent, LogEvent
from agentbox.config import Settings
from agentbox.core.data import AgentDef, SessionStore
from agentbox.core.engines.backends.base import PostRenderContext, RenderedConfig
from agentbox.core.engines.render import ConfigGenerator
from agentbox.core.execution.render import materialize_rendered_config
from agentbox.core.workspace import (
    load_capabilities,
    resolve_path,
)

from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster

if TYPE_CHECKING:
    from agentbox.core.engines.backends.base import BackendAdapter
    from agentbox.core.workspace import McpRegistry

logger = logging.getLogger(__name__)


class NoBackendAvailable(RuntimeError):
    """Raised when ``RunSetup.select_backend`` cannot pick any adapter.

    Carries the attempted names so the HTTP layer can tell the client
    *which* backend was requested and let the loader's failure-reason
    map explain why it's unavailable.
    """

    def __init__(self, *, agent_id: str, attempted: list[str]) -> None:
        self.agent_id = agent_id
        self.attempted = list(attempted)
        super().__init__(
            f"no backend available for agent {agent_id!r} (attempted: {self.attempted})"
        )


def load_workspace_permissions(
    workdir: Path,
    agent: AgentDef,
    settings: Settings,
    store: SessionStore | None = None,
) -> dict:
    """Resolve effective workspace permissions from the DB overlay.

    ``workspace_runtime_permissions`` is the single source of truth for
    built-in tools, file scopes, max_tokens, and network/write flags.
    Workspaces with no overlay row receive an empty permissions dict —
    callers downstream treat that as "no constraints declared".
    """
    if not agent.workspace or agent.workspace == "<ephemeral>":
        return {}
    if store is None:
        return {}
    try:
        overlay = store.get_workspace_runtime_permissions(agent.workspace)
    except Exception:
        return {}
    if not overlay:
        return {}
    perms: dict = {}
    if overlay.get("allowed_builtin_tools") is not None:
        perms["allowed_builtin_tools"] = overlay["allowed_builtin_tools"]
    if overlay.get("files") is not None:
        perms["files"] = overlay["files"]
    if overlay.get("max_tokens") is not None:
        perms["max_tokens"] = overlay["max_tokens"]
    if overlay.get("allow_file_write") is not None:
        perms["allow_file_write"] = bool(overlay["allow_file_write"])
    if overlay.get("allow_network") is not None:
        perms["allow_network"] = bool(overlay["allow_network"])
    return perms


class RunSetup:
    """Pre-stream setup collaborator for ``RunExecutor``.

    Owns workdir allocation, backend selection, render materialization,
    and the post-render MCP injection step. Pure helpers — no async,
    no state beyond the injected store/settings.
    """

    def __init__(
        self,
        store: SessionStore,
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
                path, ephemeral = resolve_path(agent, self.settings, self.store)
            finally:
                agent.workspace = original
            if not ephemeral:
                path.mkdir(parents=True, exist_ok=True)
                return path, session_id

        path, ephemeral = resolve_path(agent, self.settings, self.store)
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
        """Pick a backend adapter and render its config.

        Algorithm:
        1. Explicit ``backend`` from the request (highest priority).
        2. Resolved ``EffectiveRunnerConfig.backend``.
        3. ``NoBackendAvailable`` error.

        Static ``agent.runner`` is intentionally ignored; dispatch has a
        single runtime source of truth: ``EffectiveRunnerConfig``.

        Cross-domain values (runtime config, host capabilities) are
        resolved here so backends never import ``core.agents.*`` or
        ``core.workspace.*`` directly.
        """

        # Resolve cross-domain values before render so backends don't
        # import from agents / workspaces / resources domains directly.
        runtime_config = RuntimeConfig.from_agent(agent)
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
                    runtime_config=runtime_config,
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

        # materialize_rendered_config owns the exclusive mkdir (mode 0o700).
        materialize_rendered_config(rendered, run_dir)

        permissions = load_workspace_permissions(
            workdir, agent, self.settings, self.store
        )
        generator = self._make_generator()
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

    # ------------------------------------------------------------------ generator
    def _make_generator(self) -> ConfigGenerator:
        project_root = self.settings.project_root
        agentbox_toml = project_root / "agentbox.toml"
        mcp_manifest = self._try_get_mcp_manifest()
        servers = self.store.get_project_mcp_servers()
        mcp_spec = servers[0] if servers else None
        mcp_server_name = mcp_spec.name if mcp_spec else "mcp"
        mcp_url = mcp_spec.url if mcp_spec else None
        mcp_transport = str(mcp_spec.transport) if mcp_spec else "http"
        mcp_command = (
            mcp_spec.command if mcp_spec and mcp_spec.command else ["mcp_serve.sh"]
        )
        static_manifest_path: Path | None = None
        tool_manifest_path = self.store.get_tool_manifest_path()
        if tool_manifest_path:
            candidate = project_root / tool_manifest_path
            if candidate.exists():
                static_manifest_path = candidate
        return ConfigGenerator(
            agentbox_toml=agentbox_toml,
            manifest_path=static_manifest_path,
            mcp_manifest=mcp_manifest,
            mcp_server_name=mcp_server_name,
            mcp_url=mcp_url,
            mcp_transport=mcp_transport,
            mcp_command=mcp_command,
            verbose=False,
        )

    def _try_get_mcp_manifest(self):
        if self._mcp_registry is None:
            return None
        try:
            return self._mcp_registry.manifest
        except Exception:
            return None


def fail_pre_run(
    store: SessionStore,
    settings: Settings,
    broadcasters: dict[str, RunBroadcaster],
    *,
    agent: AgentDef,
    input_: str,
    workdir: Path,
    session_id: str | None,
    error_msg: str,
) -> str:
    """Create an error run record and broadcast failure before execution starts.

    Used when something during setup (workdir, profile resolution, missing
    backend) makes it impossible to launch the run task. We still create a
    row so the operator can see the failure in the UI / API.
    """
    transcripts_dir = settings.data_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
    run_id = store.create_run(
        agent_id=agent.id,
        input_=input_,
        workdir=str(workdir),
        transcript_path=str(transcript_path),
        session_id=session_id,
    )
    store.finish_run(run_id, ok=False, error=error_msg)
    broadcaster = RunBroadcaster()
    broadcasters[run_id] = broadcaster
    broadcaster.publish(
        LogEvent(run_id=run_id, level="error", message=f"Error: {error_msg}")
    )
    broadcaster.publish(DoneEvent(run_id=run_id, ok=False, error=error_msg))
    broadcaster.close()
    return run_id


__all__ = [
    "NoBackendAvailable",
    "RunSetup",
    "fail_pre_run",
    "load_workspace_permissions",
]
