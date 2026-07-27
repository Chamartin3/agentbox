"""Pre-run setup: workdir, backend selection, render, MCP injection."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox.core.agents import resolve_engine
from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.db import (
    AgentPromptResourceBindingManager,
    AgentToolGrantManager,
    ResourceBlobManager,
    ResourceVersionManager,
    SessionManager,
    WorkspaceFileResourceBindingManager,
    WorkspaceManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
)
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


@dataclass(frozen=True)
class SetupManagers:
    """Manager bundle threaded into :class:`RunSetup`."""

    workspaces: WorkspaceManager
    sessions: SessionManager
    agent_tool_grants: AgentToolGrantManager
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager
    workspace_mcp_policies: WorkspaceMcpPolicyManager
    workspace_mcp_overrides: WorkspaceMcpOverrideManager
    workspace_mcp_tool_overrides: WorkspaceMcpToolOverrideManager
    agent_prompt_resource_bindings: AgentPromptResourceBindingManager
    resource_versions: ResourceVersionManager
    resource_blobs: ResourceBlobManager


def _resolve_output_schema_content(
    agent_id: str,
    bindings_mgr: AgentPromptResourceBindingManager,
    versions_mgr: ResourceVersionManager,
    blobs_mgr: ResourceBlobManager,
) -> bytes | None:
    """Resolve the output-schema JSON bytes from the DB binding.

    Looks up the ``output_schema`` slot binding for *agent_id* and returns
    the blob content of the pinned or active version.  Returns ``None`` when
    no binding exists (agent has no DB-authoritative schema yet).
    """
    bindings = bindings_mgr.list_for_agent(agent_id)
    for b in bindings:
        if b.get("slot") == "output_schema":
            version_id: str | None = b.get("pinned_version_id") or None
            if not version_id:
                # No pinned version — resolve via the active version pointer.
                active = versions_mgr.get_active_version(b["resource_id"])
                if active is None:
                    logger.debug(
                        "output_schema binding for agent %r has no active version; skipping",
                        agent_id,
                    )
                    continue
                version_id = active["id"]
            # Try the root blob first (relative_path=""), then "schema.json".
            blob = blobs_mgr.get_blob(version_id, "") or blobs_mgr.get_blob(
                version_id, "schema.json"
            )
            if blob is not None:
                content: bytes = blob["content"]
                return content
    return None


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
        mgrs: SetupManagers,
        settings: Settings,
        mcp_registry: "McpRegistry | None",
    ) -> None:
        self._mgrs = mgrs
        self.settings = settings
        self._mcp_registry = mcp_registry

    # ------------------------------------------------------------------ workdir
    def prepare_workdir(
        self,
        agent: AgentDef,
        session_id: str | None,
        workspace_override: str | None = None,
        *,
        session_mode: str | None = None,
        fresh_workspace: bool = False,
    ) -> tuple[Path, str | None, bool]:
        """Resolve the run workdir.

        Returns (path, session_id, dispose_after_run).
        dispose_after_run=True means the workdir is a throwaway temp dir and
        should be deleted once the run finishes.
        """
        ws_lookup = self._mgrs.workspaces
        effective_mode = session_mode or "headless"

        if workspace_override:
            original = agent.workspace
            agent.workspace = workspace_override
            try:
                path, ephemeral = resolve_path(agent, self.settings, ws_lookup)
            finally:
                agent.workspace = original
            if not ephemeral:
                path.mkdir(parents=True, exist_ok=True)
                return path, session_id, False

        path, ephemeral = resolve_path(agent, self.settings, ws_lookup)

        # fresh_workspace forces a throwaway dir regardless of what the agent
        # declares; it never wipes named/provisioned workspace directories.
        if not ephemeral and not fresh_workspace:
            path.mkdir(parents=True, exist_ok=True)
            return path, session_id, False

        if effective_mode == "persistent":
            # Persistent: reuse or create a durable session workdir.
            if not fresh_workspace and session_id:
                existing = self._mgrs.sessions.get_dict(session_id)
                if existing and existing["workdir"]:
                    self._mgrs.sessions.touch(session_id)
                    return Path(existing["workdir"]), session_id, False
            self.settings.sessions_dir.mkdir(parents=True, exist_ok=True)
            sid = self._mgrs.sessions.create_session(agent.id, effective_mode, None)
            wd = self.settings.sessions_dir / sid / "workdir"
            wd.mkdir(parents=True, exist_ok=True)
            self._mgrs.sessions.set_workdir(sid, str(wd))
            return wd, sid, False

        # headless ephemeral: temp dir deleted after the run.
        self.settings.runs_dir.mkdir(parents=True, exist_ok=True)
        wd = (
            Path(tempfile.mkdtemp(prefix="run-", dir=self.settings.runs_dir))
            / "workdir"
        )
        wd.mkdir(parents=True, exist_ok=True)
        return wd, None, True

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
        output_schema_content = _resolve_output_schema_content(
            agent.id,
            self._mgrs.agent_prompt_resource_bindings,
            self._mgrs.resource_versions,
            self._mgrs.resource_blobs,
        )
        python_agent_config_view = PythonAgentConfigView(
            agent_module=python_config_raw.get("agent_module"),
            output_schema_path=python_config_raw.get("output_schema_path"),
            output_schema_content=output_schema_content,
        )

        ws_id = agent.workspace

        # Per-workspace credential materialization. A workspace that has
        # enabled ≥1 credential opts into least privilege: `creds` becomes the
        # exact env-var set that workspace granted, and the adapter scrubs all
        # other provider keys. An unconfigured workspace → `creds=None` → the
        # run inherits the full container env (legacy, non-breaking).
        # Lazy import avoids a load-time core.execution ↔ core.service cycle.
        from agentbox.core.service.credentials import CredentialService  # noqa: PLC0415

        creds: dict[str, str] | None = None
        if ws_id:
            _cs = CredentialService()
            if _cs.list_workspace_credentials(ws_id):
                creds = _cs.resolve_env_for_workspace(ws_id)

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
                    self._mgrs.workspace_file_resource_bindings,
                    self._mgrs.workspace_mcp_policies,
                    self._mgrs.workspace_mcp_overrides,
                    self._mgrs.workspace_mcp_tool_overrides,
                    self._mcp_registry,
                    declared_tools=adapter.declared_tools(),
                    project_server_names=[s.name for s in self._mgrs.settings.get_project_mcp_servers()],
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
                creds=creds,
                runner_config=runner_config,
                composed=_composed_view(composed),
                runtime_config=runtime_config_view,
                python_agent_config=python_agent_config_view,
                ws_allowed_tools=ws_allowed_tools,
                extra_env=None,
            )
            return adapter, rendered

        raise NoBackendAvailable(agent_id=agent.id, attempted=candidates)

    # ------------------------------------------------------------------ MCP grants
    def resolve_agent_tool_grants(self, agent_id: str) -> set[str] | None:
        try:
            # list_for_agent(include_revoked=False) already excludes revoked rows
            grants = self._mgrs.agent_tool_grants.list_for_agent(agent_id)
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
    "SetupManagers",
    "fail_pre_run",
]
