"""RunExecutor — orchestrates a single agent run end-to-end.

Responsibilities:
- materialize a tmp or persistent workdir for the run
- select and configure a BackendAdapter
- stream RunEvents into both an in-memory broadcast queue and the on-disk
  transcript JSONL
- aggregate usage events into the SessionStore
- validate output against JSON Schema and retry on failure
- invoke guardrails after completion
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.api.events import (
    DoneEvent,
    GuardrailEvent,
    LogEvent,
    RunEvent,
    UsageEvent,
)
from agentbox.api.webhooks import schedule_webhook
from agentbox.config import Settings
from agentbox.core.agent_config import ExecutionConfig
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.config_generation import ConfigGenerator
from agentbox.core.constants import DEFAULT_RUNNER_TIMEOUT_SECONDS, RunStatus
from agentbox.core.data import SessionStore
from agentbox.core.data.schema import runs as _runs_table
from agentbox.core.definitions import AgentDef, DefinitionLoader
from agentbox.core.guardrails.base import GuardrailContext
from agentbox.core.host_env.capabilities import CAPABILITIES as _HOST_ENV_CAPABILITIES
from agentbox.core.plugins import get_backend, get_guardrail
from agentbox.core.prompt_capture import build_fragments, fragments_to_json
from agentbox.core.render import materialize_rendered_config
from agentbox.core.resources.prompt_resolver import resolve_prompt
from agentbox.core.resources.subagent_render import materialize_subagents
from agentbox.core.resources.workspace_materialize import materialize_workspace
from agentbox.core.run_prep import (
    prompt_resolution_to_snapshot,
    render_env_doc,
    resolve_agent_prompt_bindings,
    resolve_workspace_resources,
    resolve_workspace_subagents,
    workspace_outcomes_to_snapshot,
)
from agentbox.core.runner_profiles import (
    EffectiveRunnerConfig,
    RunnerProfileResolver,
)
from agentbox.core.streaming.session import RunStreamSession
from agentbox.core.validation import extract_json
from agentbox.core.versioning.drift import check_drift, startup_sweep
from agentbox.core.workspaces import resolve_path

if TYPE_CHECKING:
    from agentbox.core.backends.base import BackendAdapter, BackendRunResult
    from agentbox.core.mcp.registry import McpRegistry

logger = logging.getLogger(__name__)


async def _adapter_run_into_session(
    adapter: Any,
    rendered: RenderedConfig,
    input_: str,
    session: RunStreamSession,
) -> BackendRunResult:
    """Invoke ``adapter.run_into_session`` or bridge a legacy iterator backend.

    Adapters that inherit from :class:`BackendAdapter` get the default
    iterator-bridge implementation for free. Duck-typed adapters used
    in tests (or older external backends that predate the bridge)
    expose only ``run()`` returning an ``AsyncIterator[RunEvent]``;
    this helper pumps them into the session manually so the executor's
    single entry point keeps working.
    """
    from agentbox.core.backends.base import BackendRunResult

    if hasattr(adapter, "run_into_session"):
        return await adapter.run_into_session(rendered, input_, session)

    # Duck-typed fallback — mirror the default bridge in BackendAdapter.
    result = BackendRunResult(ok=False)
    async for ev in adapter.run(rendered, input_, session.run_id):
        if isinstance(ev, DoneEvent):
            result = BackendRunResult(
                ok=ev.ok,
                exit_code=ev.exit_code,
                error=ev.error,
                status=ev.status,
            )
            continue
        session.emit(ev)
    return result


# Substring markers that identify expected, agent-level failures (vs.
# unexpected executor/runner crashes). When ``final_error`` matches any
# of these, the run is classified as ``failed`` rather than ``error``.
# Mirrors the patterns in ``core/runners/_rate_limit.py`` but operates
# on the final aggregated error string after the runner has surfaced it.
_FAILED_ERROR_MARKERS: tuple[str, ...] = (
    "rate limit",
    "rate-limit",
    "rate_limit",
    "ratelimit",
    " 429",
    "429:",
    "quota",
    "overloaded",
    "insufficient_quota",
    "FreeUsageLimitError",
    "CreditsError",
    "AI_APICallError",
    "AuthError",
    "UnauthorizedError",
    "invalid_api_key",
    "invalid api key",
    "authentication_error",
    "authentication error",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectTimeout",
    "ReadTimeout",
    "ECONNREFUSED",
    "ECONNRESET",
    "output validation failed",
    # pydantic-ai surfaces structured-output validation exhaustion as
    # ``UnexpectedModelBehavior: Exceeded maximum output retries (N)`` —
    # the model couldn't produce schema-compliant output. Treat as a
    # validation-shaped failure rather than a runner crash.
    "exceeded maximum output retries",
)


def _classify_terminal_error(err: str | None) -> str | None:
    """Map a final error string to ``failed`` when it matches a known
    expected-failure marker (rate-limit, auth, connection, validation).

    Returns ``RunStatus.FAILED.value`` on a match, else ``None`` (caller
    keeps whatever status it already had — typically ``error``).
    """
    if not err:
        return None
    lower = err.lower()
    for marker in _FAILED_ERROR_MARKERS:
        if marker.lower() in lower:
            return RunStatus.FAILED.value
    return None


def _load_workspace_permissions(
    workdir: Path,
    agent: AgentDef,
    loader: DefinitionLoader,
    settings: Settings,
    store: SessionStore | None = None,
) -> dict:
    """Resolve effective workspace permissions: WorkspaceDef <- DB overlay.

    1. Manifest defaults from ``WorkspaceDef``.
    2. DB overlay row from ``workspace_runtime_permissions`` (single source
       of truth for built-in tools, file scopes, max_tokens, flags).
    3. ``capabilities.json`` is no longer consulted — it is a derived
       artifact written by the workspaces route + config generator.
    """
    try:
        if not agent.workspace or agent.workspace == "<ephemeral>":
            return {}
        ws_def = loader.get_workspace(agent.workspace)
        if ws_def is None:
            return {}
        perms: dict = {
            "allowed_tools": list(ws_def.allowed_tools),
            "allowed_builtin_tools": list(ws_def.allowed_builtin_tools),
            "files": [f.model_dump() for f in ws_def.files],
            "max_tokens": ws_def.max_tokens,
            "allow_file_write": ws_def.allow_file_write,
            "allow_network": ws_def.allow_network,
        }
        if store is not None:
            overlay = store.get_workspace_runtime_permissions(agent.workspace)
            if overlay:
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
    except Exception:
        return {}


class NoBackendAvailable(RuntimeError):
    """Raised when ``_select_backend`` cannot pick any registered adapter.

    Carries the attempted names so the HTTP layer can tell the client
    *which* backend was requested and let the loader's failure-reason
    map explain why it's unavailable.
    """

    def __init__(self, *, agent_id: str, attempted: list[str]) -> None:
        self.agent_id = agent_id
        self.attempted = list(attempted)
        super().__init__(
            f"no backend available for agent {agent_id!r} "
            f"(attempted: {self.attempted})"
        )


class RunBroadcaster:
    """In-memory pub/sub for one run's event stream."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[RunEvent | None]] = []
        self._history: list[RunEvent] = []
        self._closed = False

    def subscribe(self) -> asyncio.Queue[RunEvent | None]:
        q: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        for ev in self._history:
            q.put_nowait(ev)
        if self._closed:
            q.put_nowait(None)
        else:
            self._subscribers.append(q)
        return q

    def publish(self, ev: RunEvent) -> None:
        self._history.append(ev)
        for q in self._subscribers:
            q.put_nowait(ev)

    def close(self) -> None:
        self._closed = True
        for q in self._subscribers:
            q.put_nowait(None)
        self._subscribers.clear()


class RunExecutor:
    def __init__(
        self,
        store: SessionStore,
        settings: Settings,
        loader: DefinitionLoader,
        mcp_registry: McpRegistry | None = None,
    ):
        self.store = store
        self.settings = settings
        self.loader = loader
        self._mcp_registry = mcp_registry
        self._broadcasters: dict[str, RunBroadcaster] = {}
        # Strong references to in-flight run tasks. asyncio only holds
        # weak references to tasks, so without this set the GC can collect
        # a long-running run mid-flight, skipping the finally block that
        # persists final status and fires the webhook.
        self._tasks: set[asyncio.Task[None]] = set()
        # run_id → task lookup for operator cancellation. Kept in sync
        # with ``_tasks`` (entries removed on task completion).
        self._run_tasks: dict[str, asyncio.Task[None]] = {}
        # Runner profile resolver — cheap to instantiate, used on every run.
        self._profile_resolver = RunnerProfileResolver()

    def _make_generator(self) -> ConfigGenerator:
        manifest = self.loader.load()
        agentbox_toml = self.loader.manifest_path
        mcp_manifest = self._try_get_mcp_manifest()
        mcp_spec = manifest.mcp_servers[0] if manifest.mcp_servers else None
        mcp_server_name = mcp_spec.name if mcp_spec else "mcp"
        mcp_url = mcp_spec.url if mcp_spec else None
        mcp_transport = str(mcp_spec.transport) if mcp_spec else "http"
        mcp_command = mcp_spec.command if mcp_spec and mcp_spec.command else ["mcp_serve.sh"]
        # Static tool_manifest.json fallback (resolved relative to
        # manifest.toml's parent) — used by discovery when the runtime
        # MCP manifest is empty (server down, transport mismatch, etc.).
        static_manifest_path: Path | None = None
        if manifest.tool_manifest_path:
            candidate = agentbox_toml.parent / manifest.tool_manifest_path
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

    def broadcaster(self, run_id: str) -> RunBroadcaster | None:
        return self._broadcasters.get(run_id)

    async def execute(
        self,
        agent: AgentDef,
        input_: str,
        session_id: str | None = None,
        workspace_override: str | None = None,
        timeout_seconds: int | None = None,
        webhook_url: str | None = None,
        runner_override: str | None = None,
        backend: str | None = None,
        variables: dict[str, Any] | None = None,
        runner_embedded: bool = False,
        runner_profile: str | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> str:
        workdir, session_id = self._prepare_workdir(
            agent, session_id, workspace_override
        )

        if backend is None and runner_override is not None:
            backend = runner_override
        if webhook_url is not None:
            agent = agent.model_copy(update={"webhook_url": webhook_url})

        # --- resource prep (Plan 08 Phase 1) ---------------------------------
        _resource_snapshot_entries: list[dict] = []
        _workspace_id = agent.workspace if agent.workspace != "<ephemeral>" else None
        if _workspace_id:
            try:
                ws_bindings = resolve_workspace_resources(self.store, _workspace_id)
                if ws_bindings:
                    outcomes = materialize_workspace(
                        workdir, ws_bindings,
                        cache_root=self.settings.resource_cache_dir,
                    )
                    _resource_snapshot_entries.extend(workspace_outcomes_to_snapshot(outcomes))
            except Exception:
                logger.exception(
                    "executor: workspace resource materialization failed for workspace %r",
                    _workspace_id,
                )

            try:
                env_doc_entries = render_env_doc(self.store, _workspace_id, workdir)
                _resource_snapshot_entries.extend(env_doc_entries)
            except Exception:
                logger.exception(
                    "executor: env doc rendering failed for workspace %r",
                    _workspace_id,
                )

            # Workspace subagents (RESOURCES_PLAN E3): write
            # .{claude,opencode,codex}/agents/<alias>.md per registered
            # subagent so the active backend can delegate to them.
            try:
                resolved_subagents = resolve_workspace_subagents(
                    self.store, _workspace_id
                )
                if resolved_subagents:
                    sub_outcomes = materialize_subagents(workdir, resolved_subagents)
                    for o in sub_outcomes:
                        _resource_snapshot_entries.append(
                            {
                                "role": "workspace_subagent",
                                "workspace_id": o.workspace_id,
                                "agent_id": o.agent_id,
                                "alias": o.alias,
                                "files_written": o.files_written,
                            }
                        )
            except Exception:
                logger.exception(
                    "executor: workspace subagent materialization failed for workspace %r",
                    _workspace_id,
                )

        # --- composition path ------------------------------------------------
        composed_result = None
        if agent.composition is not None and variables is not None:
            from agentbox.core.composition.loader import (
                load_bundle_from_bindings,
            )

            manifest = self.loader.load()
            shared_roots = {
                k: self.settings.project_root / v
                for k, v in (manifest.shared_assets or {}).items()
            }

            # DB-as-source-of-truth (Plan 18): bundle inputs come from
            # ``agent_prompt_resource_bindings`` first, with a fallback
            # to ``agent_versions.prompt_content`` for agents that have
            # not been migrated to bindings. The on-disk bundle is no
            # longer read at runtime — only at import time.
            bundle = load_bundle_from_bindings(
                agent_id=agent.id,
                store=self.store,
            )
            composed_result = bundle.compose(variables, shared_roots)

            # Append validation-engine hint to system prompt when a schema
            # is present so the LLM knows how strictly its output will be
            # checked.
            system_text = composed_result.system
            if composed_result.schema is not None:
                engine = ExecutionConfig.from_agent(agent).output_validation_engine
                from agentbox.core.composition import (
                    _append_validation_engine_hint,
                )

                system_text = _append_validation_engine_hint(system_text, engine)

            # Attach composed metadata so backend adapters can read it
            agent = agent.model_copy(deep=True)
            agent.__dict__["_composed_system"] = system_text
            agent.__dict__["_composed_user"] = composed_result.user
            agent.__dict__["_composed_schema"] = composed_result.schema
            agent.__dict__["_composed_bundle_sha"] = composed_result.bundle_sha
            input_ = composed_result.user

        # Wire output schema into runner spec for the executor's retry loop.
        # Runs whether or not the composition path executed — callers that
        # pass a raw `input_` (no `variables`) still get schema validation
        # when the agent declares an output schema. Mirrors the composer's
        # auto-detection: bundles shipping output_schema.json without
        # declaring it in [composition].output_schema still engage validation.
        comp = agent.composition
        if comp is not None:
            if composed_result is None:
                agent = agent.model_copy(deep=True)
            # Schema location: when composition resolved a schema (via
            # bindings or agent_versions), it's already attached to
            # ``agent._composed_schema``. The legacy
            # ``runner.output_schema_path`` only matters when no
            # composed schema is present — in that case there's nothing
            # to validate against and ``_validate_output`` returns "off".
            agent.__dict__["_composed_validation_mode"] = comp.output_validation

        # --- prompt resource binding substitution (Plan 08 Phase 1) ----------
        prompt_bindings: list[dict] = []
        try:
            prompt_bindings = resolve_agent_prompt_bindings(self.store, agent.id)
            if prompt_bindings:
                composed_system = agent.__dict__.get("_composed_system")
                if composed_system is not None:
                    resolution = resolve_prompt(composed_system, prompt_bindings)
                    agent.__dict__["_composed_system"] = resolution.rendered_prompt
                    _resource_snapshot_entries.extend(
                        prompt_resolution_to_snapshot(resolution)
                    )
                    for marker in resolution.unresolved_markers:
                        logger.warning(
                            "executor: unresolved prompt resource marker {{resource:%s}} for agent %r",
                            marker,
                            agent.id,
                        )
                else:
                    # Non-composition path: resolve against inline/file prompt if present
                    inline_prompt = agent.prompt
                    if inline_prompt:
                        resolution = resolve_prompt(inline_prompt, prompt_bindings)
                        agent = agent.model_copy(
                            update={"prompt": resolution.rendered_prompt}
                        )
                        _resource_snapshot_entries.extend(
                            prompt_resolution_to_snapshot(resolution)
                        )
                        for marker in resolution.unresolved_markers:
                            logger.warning(
                                "executor: unresolved prompt resource marker {{resource:%s}} for agent %r",
                                marker,
                                agent.id,
                            )
        except Exception:
            logger.exception(
                "executor: prompt resource binding resolution failed for agent %r",
                agent.id,
            )

        # Wire output_schema binding → _composed_schema for runtime validation.
        # Covers legacy_dir agents that declare output schemas via resource
        # bindings (sync_agent_schemas) but have no [composition] block.
        if prompt_bindings and not isinstance(agent.__dict__.get("_composed_schema"), dict):
            for _b in prompt_bindings:
                if _b.get("slot") != "output_schema":
                    continue
                for _blob in _b.get("blobs") or []:
                    _raw = (_blob.get("content_text") or "").strip()
                    if not _raw:
                        continue
                    try:
                        _schema = json.loads(_raw)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            "executor: failed to parse output_schema binding for agent %r",
                            agent.id,
                        )
                        continue
                    if isinstance(_schema, dict):
                        agent.__dict__["_composed_schema"] = _schema
                    break
                break

        # Resolve effective runner config and select backend adapter
        try:
            effective = self._profile_resolver.resolve(
                agent=agent,
                store=self.store,
                runner_profile_id=runner_profile,
                runner_config=runner_config,
                backend_override=backend,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return self._fail_pre_run(agent, input_, workdir, session_id, str(exc))

        # Require a bound runner profile only when the caller did not
        # explicitly pick a backend (e.g. via the API ``backend=`` override
        # or programmatic ``execute(..., backend=...)`` from tests).
        if effective.backend is None and backend is None:
            error_msg = (
                f"agent {agent.id!r} has no runner profile bound. "
                "Assign a runner profile in the UI (Agents → Runner Profile)."
            )
            return self._fail_pre_run(agent, input_, workdir, session_id, error_msg)

        adapter, rendered = self._select_backend(
            agent, workdir, backend, runner_config=effective
        )
        rendered, run_dir = self._render_for_run(adapter, agent, workdir, rendered)

        # --- host-env MCP server injection (Plan 08 Phase 3) -----------------
        _host_env_grants: dict | None = None
        if _workspace_id:
            try:
                resolved_he = self.store.resolve_workspace_host_env(_workspace_id)
                grants = resolved_he.get("grants") or {}
                # Only inject if there's more than the default-granted workspace_info cap
                non_default = {k for k, v in _HOST_ENV_CAPABILITIES.items() if not v.default_granted}
                if grants.keys() & non_default:
                    _host_env_grants = grants
                    self._inject_host_env_mcp(
                        run_dir=run_dir,
                        grants=grants,
                        workspace_id=_workspace_id,
                        workdir=workdir,
                    )
            except Exception:
                logger.exception(
                    "executor: host-env MCP injection failed for workspace %r",
                    _workspace_id,
                )

        transcripts_dir = self.settings.data_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
        run_id = self.store.create_run(
            agent_id=agent.id,
            input_=input_,
            workdir=str(workdir),
            transcript_path=str(transcript_path),
            session_id=session_id,
            config_digest=rendered.digest,
            runner_profile_id=effective.profile_id,
        )

        # Snapshot the resolved runner config — historical fact, never
        # updated. UI reads this so renaming/rebinding/deleting the
        # bound profile doesn't rewrite what the run page displays.
        try:
            self.store.save_run_runner_snapshot(
                run_id,
                self._build_runner_snapshot(
                    effective=effective,
                    rendered_model=rendered.model,
                    backend_override=backend,
                    runner_override=runner_override,
                    runner_profile_id_param=runner_profile,
                    runner_config_param=runner_config,
                    timeout_override=timeout_seconds,
                ),
            )
        except Exception:
            logger.exception(
                "failed to persist runner_snapshot for run %s", run_id
            )

        # Record the effective model immediately at run creation — before
        # the runner task starts — so every run has a model name in the
        # usage table regardless of backend, status, or whether the
        # runner ever emits a UsageEvent. ``rendered.model`` is populated
        # from EffectiveRunnerConfig or the backend default.
        if rendered.model:
            try:
                self.store.record_usage(run_id, {"model": rendered.model})
            except Exception:
                logger.exception(
                    "failed to pre-record model for run %s", run_id
                )

        # Persist conversation metadata from the backend adapter
        conv_format: str | None = getattr(adapter, "conversation_format", None)
        conv_uri: str | None = None
        if conv_format:
            conv_meth = getattr(adapter, "conversation_uri", None)
            if conv_meth is not None:
                conv_uri = conv_meth(
                    run_id=run_id, transcript_path=str(transcript_path)
                )
        self.store.set_run_conversation(run_id, conv_format, conv_uri)

        # Save composition metadata
        if composed_result is not None:
            snapshot = {
                "bundle_sha": composed_result.bundle_sha,
                "schema_sha": composed_result.schema_sha,
                "references": [
                    {"path": str(r) if isinstance(r, str) else r["path"]}
                    for r in (agent.composition.references if agent.composition else [])
                ],
            }
            self.store.save_run_composition(
                run_id=run_id,
                composition_snapshot=snapshot,
                rendered_prompt={
                    "system": composed_result.system,
                    "user": composed_result.user,
                    "schema": composed_result.schema,
                },
                variables=variables or {},
            )

        # Persist resource + MCP snapshots (Plan 08 Phase 1+3)
        _mcp_snapshot: dict | None = None
        if _workspace_id:
            try:
                manifest = self.loader.load()
                manifest_servers = [
                    {"name": s.name, "config": {"url": s.url, "transport": str(s.transport)}}
                    for s in (manifest.mcp_servers or [])
                ]
                _mcp_snapshot = self.store.resolve_workspace_mcp(
                    _workspace_id, manifest_servers
                )
                if _host_env_grants:
                    _mcp_snapshot["host_env_grants"] = list(_host_env_grants.keys())
                    _mcp_snapshot["host_env_injected"] = True
            except Exception:
                logger.exception(
                    "executor: MCP snapshot capture failed for workspace %r", _workspace_id
                )
        try:
            self.store.save_resource_snapshots(
                run_id,
                resource_snapshot=_resource_snapshot_entries if _resource_snapshot_entries else None,
                mcp_snapshot=_mcp_snapshot,
            )
        except Exception:
            logger.exception("executor: failed to persist snapshots for run %s", run_id)

        # Stamp run with current agent version
        self._stamp_run_agent_version(run_id, agent)

        # Embedded runner: caller will post snapshot later
        if runner_embedded:
            if variables:
                self.store.save_run_composition(
                    run_id=run_id,
                    composition_snapshot=None,
                    rendered_prompt=None,
                    variables=variables,
                )
            return run_id

        broadcaster = RunBroadcaster()
        self._broadcasters[run_id] = broadcaster
        try:
            frags = build_fragments(
                agent=agent,
                user_input=input_,
                project_root=self.settings.project_root,
                store=self.store,
            )
            self.store.save_run_prompt(run_id, fragments_to_json(frags))
        except Exception:
            pass
        task = asyncio.create_task(
            self._run(
                run_id,
                adapter,
                rendered,
                agent,
                input_,
                workdir,
                run_dir,
                transcript_path,
                broadcaster,
                effective=effective,
            )
        )
        self._tasks.add(task)
        self._run_tasks[run_id] = task

        def _on_task_done(t: asyncio.Task[None]) -> None:
            self._tasks.discard(t)
            self._run_tasks.pop(run_id, None)
            if not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    logger.exception(
                        "run task crashed", exc_info=(type(exc), exc, exc.__traceback__)
                    )

        task.add_done_callback(_on_task_done)
        return run_id

    async def cancel_run(self, run_id: str) -> bool:
        """Cancel an in-progress run.

        Marks the run as ``incomplete`` in the store first (so the
        executor's ``finally`` finish_run becomes a no-op — it only
        updates rows still in ``running``), emits a terminal ``DoneEvent``
        to any WS subscribers, then cancels the asyncio task driving the
        subprocess. The subprocess transport will be torn down as the
        cancellation unwinds, which sends SIGKILL to the backend process
        via asyncio's subprocess transport shutdown.

        Returns ``True`` if a running task was found and cancellation was
        initiated, ``False`` otherwise.
        """
        task = self._run_tasks.get(run_id)
        if task is None or task.done():
            return False

        error_msg = "cancelled by operator"
        try:
            self.store.finish_run(
                run_id,
                ok=False,
                error=error_msg,
                status=RunStatus.INCOMPLETE.value,
            )
        except Exception:
            logger.exception("cancel_run: failed to persist incomplete status for %s", run_id)

        broadcaster = self._broadcasters.get(run_id)
        if broadcaster is not None:
            with contextlib.suppress(Exception):
                broadcaster.publish(
                    LogEvent(run_id=run_id, level="warn", message=error_msg)
                )
                broadcaster.publish(
                    DoneEvent(
                        run_id=run_id,
                        ok=False,
                        error=error_msg,
                        status=RunStatus.INCOMPLETE.value,
                    )
                )

        task.cancel()
        return True

    def _fail_pre_run(
        self,
        agent: AgentDef,
        input_: str,
        workdir: Path,
        session_id: str | None,
        error_msg: str,
    ) -> str:
        """Create an error run record and broadcast failure events before execution starts."""
        transcripts_dir = self.settings.data_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts_dir / f"{uuid.uuid4().hex}.jsonl"
        run_id = self.store.create_run(
            agent_id=agent.id,
            input_=input_,
            workdir=str(workdir),
            transcript_path=str(transcript_path),
            session_id=session_id,
        )
        self.store.finish_run(run_id, ok=False, error=error_msg)
        broadcaster = RunBroadcaster()
        self._broadcasters[run_id] = broadcaster
        broadcaster.publish(
            LogEvent(run_id=run_id, level="error", message=f"Error: {error_msg}")
        )
        broadcaster.publish(DoneEvent(run_id=run_id, ok=False, error=error_msg))
        broadcaster.close()
        return run_id

    def _select_backend(
        self,
        agent: AgentDef,
        workdir: Path,
        backend_override: str | None = None,
        runner_config: EffectiveRunnerConfig | None = None,
    ) -> tuple[BackendAdapter, RenderedConfig]:
        """Pick a backend adapter and render its config.

        Algorithm:
        1. Explicit ``backend`` from the request (highest priority).
        2. Resolved ``EffectiveRunnerConfig.backend``.
        3. ``NO_BACKEND_AVAILABLE`` error.

        Static ``agent.runner`` is intentionally ignored; dispatch has a
        single runtime source of truth: ``EffectiveRunnerConfig``.
        """

        def _try_backend(name: str) -> BackendAdapter | None:
            try:
                cls = get_backend(name)
                inst = cls()
            except KeyError:
                return None
            return inst  # type: ignore[return-value]

        candidates: list[str] = []

        if backend_override:
            candidates = [backend_override]
        elif runner_config is not None and runner_config.backend:
            candidates = [runner_config.backend]

        for name in candidates:
            adapter = _try_backend(name)
            if adapter is not None:
                rendered = adapter.render(
                    agent, workdir, runner_config=runner_config
                )
                return adapter, rendered

        # Carry the list of attempted names so the HTTP layer can tell the
        # caller *which* backend was asked for and why it's unavailable.
        raise NoBackendAvailable(agent_id=agent.id, attempted=candidates)

    def _build_runner_snapshot(
        self,
        *,
        effective: EffectiveRunnerConfig,
        rendered_model: str | None,
        backend_override: str | None,
        runner_override: str | None,
        runner_profile_id_param: str | None,
        runner_config_param: dict[str, Any] | None,
        timeout_override: int | None,
    ) -> dict[str, Any]:
        """Compose the append-only runner_snapshot dict for a run.

        Captures everything the run-detail UI needs to render what
        actually executed: backend, model, timeout, provider, extra_args,
        the resolution source, and any per-run overrides that were
        applied. Profile name is looked up best-effort.
        """
        from agentbox.core.data.records import now_iso

        profile_name: str | None = None
        if effective.profile_id:
            try:
                profile = self.store.get_runner_profile(effective.profile_id)
                if profile is not None:
                    profile_name = getattr(profile, "name", None) or (
                        profile.get("name") if hasattr(profile, "get") else None
                    )
            except Exception:
                logger.debug(
                    "could not resolve profile name for %s", effective.profile_id
                )

        overrides_applied: dict[str, Any] = {}
        if backend_override:
            overrides_applied["backend"] = backend_override
        if runner_override:
            overrides_applied["runner_kind"] = runner_override
        if runner_profile_id_param:
            overrides_applied["runner_profile_id"] = runner_profile_id_param
        if runner_config_param:
            overrides_applied["runner_config"] = runner_config_param
        if timeout_override:
            overrides_applied["timeout_seconds"] = timeout_override

        return {
            "profile_id": effective.profile_id,
            "profile_name": profile_name,
            "backend": effective.backend,
            "model": rendered_model or effective.model,
            "timeout_seconds": effective.timeout_seconds,
            "provider": effective.provider,
            "extra_args": list(effective.extra_args or []),
            "source": effective.source,
            "overrides_applied": overrides_applied,
            "captured_at": now_iso(),
        }

    def _prepare_workdir(
        self,
        agent: AgentDef,
        session_id: str | None,
        workspace_override: str | None = None,
    ) -> tuple[Path, str | None]:
        if workspace_override:
            original = agent.workspace
            agent.workspace = workspace_override
            try:
                path, ephemeral = resolve_path(agent, self.settings, self.loader)
            finally:
                agent.workspace = original
            if not ephemeral:
                path.mkdir(parents=True, exist_ok=True)
                return path, session_id

        path, ephemeral = resolve_path(agent, self.settings, self.loader)
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

    def _render_for_run(
        self,
        adapter: BackendAdapter,
        agent: AgentDef,
        workdir: Path,
        rendered: RenderedConfig,
    ) -> tuple[RenderedConfig, Path]:
        run_dir = self.settings.runs_tmpfs_dir / uuid.uuid4().hex

        # materialize_rendered_config owns the exclusive mkdir (mode 0o700).
        materialize_rendered_config(rendered, run_dir)

        permissions = _load_workspace_permissions(
            workdir, agent, self.loader, self.settings, self.store
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

    def _inject_host_env_mcp(
        self,
        run_dir: Path,
        grants: dict,
        workspace_id: str,
        workdir: Path,
    ) -> None:
        """Patch claude_mcp.json in run_dir to include the host-env stdio server.

        Claude Code / OpenCode spawn the server themselves when they see it in
        the MCP config. We pass the effective grants + run context via env vars
        so the server process can enforce them and write to the audit log.
        """
        import json as _json
        import sys

        mcp_path = run_dir / "claude_mcp.json"
        if not mcp_path.exists():
            mcp_data: dict = {"mcpServers": {}}
        else:
            mcp_data = _json.loads(mcp_path.read_text())
        mcp_data.setdefault("mcpServers", {})

        env_vars: dict[str, str] = {
            "AGENTBOX_HOST_ENV_GRANTS_JSON": _json.dumps(grants),
            "AGENTBOX_HOST_ENV_WORKSPACE_ID": workspace_id,
            "AGENTBOX_HOST_ENV_WORKDIR": str(workdir),
            "AGENTBOX_DB_PATH": str(self.settings.db_path),
        }
        mcp_data["mcpServers"]["agentbox-host-env"] = {
            "command": sys.executable,
            "args": ["-m", "agentbox.mcp_servers.host_env"],
            "env": env_vars,
        }
        mcp_path.write_text(
            _json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.debug(
            "executor: injected host-env MCP server for workspace %r with caps: %s",
            workspace_id,
            list(grants.keys()),
        )

    @staticmethod
    def _cleanup_run_dir(run_dir: Path | None) -> None:
        if run_dir is None:
            return
        if os.environ.get("AGENTBOX_KEEP_RUN_DIRS") == "1":
            return
        shutil.rmtree(run_dir, ignore_errors=True)

    async def _run(
        self,
        run_id: str,
        adapter: BackendAdapter,
        rendered: RenderedConfig,
        agent: AgentDef,
        input_: str,
        workdir: Path,
        run_dir: Path,
        transcript_path: Path,
        broadcaster: RunBroadcaster,
        effective: EffectiveRunnerConfig | None = None,
    ) -> None:
        from agentbox.core.agent_config import ExecutionConfig, PythonAgentConfig

        current_input = input_

        final_ok = False
        final_error: str | None = None
        final_status: str | None = None
        output: str | None = None
        validation_status: str | None = None
        validation_errors: list[str] | None = None
        schema_validated_via: str | None = None

        exec_cfg = ExecutionConfig.from_agent(agent)
        python_cfg = PythonAgentConfig.from_agent(agent)

        error_retries_left = exec_cfg.max_error_retries or 0
        validation_retries_left = exec_cfg.max_validation_retries or 0
        # Cap total attempts to avoid infinite loops.
        max_attempts = 1 + error_retries_left + validation_retries_left

        timeout = (
            effective.timeout_seconds if effective is not None else None
        ) or DEFAULT_RUNNER_TIMEOUT_SECONDS

        # ``timeout`` is the per-RUN wall-clock budget, shared across every
        # error/validation retry attempt below — not a per-attempt allowance.
        # The old behaviour granted each attempt its own ``timeout`` window,
        # which let a 400s timeout produce 27-minute runs when the LLM kept
        # failing schema validation (3 retries at ~6 min each + the original).
        # Users read "timeout" as "this run will finish within N seconds";
        # a shared deadline honours that. A slow attempt 1 can now starve
        # attempt 2 — that's the correct trade-off: the configured timeout
        # is the *budget*, not the *per-iteration cap*.
        deadline = asyncio.get_event_loop().time() + timeout

        # Single fan-out point for transcript + WS broadcast + output_text
        # accumulation. Replaces three lines of plumbing scattered across the
        # run loop and enforces "DoneEvent is the LAST event emitted" — UIs
        # treat ``done`` as terminal, so post-run ``ValidationEvent``s
        # previously raced the close and were lost from WS subscribers.
        session = RunStreamSession(
            run_id=run_id,
            broadcaster=broadcaster,
            transcript_path=transcript_path,
        )
        session.add_observer(
            lambda ev: self.store.record_usage(run_id, ev.model_dump())
            if isinstance(ev, UsageEvent)
            else None
        )

        try:
            # Model is pre-recorded at run creation (see ``execute``); no
            # need to re-record here. UsageEvents from the runner refine
            # token/cost; model is preserved by COALESCE in record_usage.
            with session:
                for attempt in range(max_attempts):
                    session.output_text.clear()
                    run_error: str | None = None

                    # Honour the shared wall-clock deadline computed above.
                    # If a prior attempt already exhausted the budget, raise
                    # synthetic TimeoutError immediately rather than waiting
                    # for ``asyncio.timeout_at`` to fire on a no-op await.
                    if asyncio.get_event_loop().time() >= deadline:
                        run_error = (
                            f"timeout after {timeout}s "
                            f"(budget exhausted across {attempt} attempt"
                            f"{'s' if attempt != 1 else ''})"
                        )
                        final_error = run_error
                        final_ok = False
                        final_status = RunStatus.TIMEOUT.value
                        session.emit_timeout(
                            timeout_seconds=timeout, error=run_error
                        )
                        session.emit_log(level="error", message=run_error)
                        break

                    try:
                        async with asyncio.timeout_at(deadline):
                            # Backend pushes events through the session
                            # (which enforces DoneEvent-last ordering) and
                            # returns the terminal status. The default
                            # ``run_into_session`` pump intercepts the
                            # backend's DoneEvent so it doesn't reach WS
                            # clients before validation runs.
                            #
                            # Note: the previous loop also early-broke on
                            # fatal LogEvents (rate-limit / auth / quota
                            # markers) to cut off subprocess output sooner.
                            # We've dropped that here — the backend still
                            # surfaces the error via its own DoneEvent, and
                            # ``_classify_terminal_error`` below reclassifies
                            # the run as ``failed`` based on the error
                            # string. Responsiveness regression on stuck
                            # rate-limited subprocesses is the trade-off;
                            # the per-run timeout still bounds total wall
                            # time. See ``detect_in_text_line``.
                            backend_result = await _adapter_run_into_session(
                                adapter, rendered, current_input, session
                            )
                            final_ok = backend_result.ok
                            final_error = backend_result.error
                            final_status = backend_result.status
                    except TimeoutError:
                        run_error = f"timeout after {timeout}s"
                        final_error = run_error
                        final_ok = False
                        final_status = RunStatus.TIMEOUT.value
                        if timeout is not None:
                            session.emit_timeout(
                                timeout_seconds=timeout, error=run_error
                            )
                    except Exception as exc:
                        import traceback as _tb
                        tb_text = _tb.format_exc()
                        run_error = f"executor error: {type(exc).__name__}: {exc}\n{tb_text}"
                        final_error = run_error
                        final_ok = False
                        logging.getLogger("agentbox.executor").exception(
                            "runner crashed for run %s", run_id
                        )

                    if run_error:
                        session.emit_log(level="error", message=run_error)

                    output = "\n".join(session.output_text).strip() or None

                    # When the agent wrote structured output to a file
                    # instead of returning it inline (e.g. opencode with
                    # write tools), prefer the file content if the text
                    # output doesn't parse as JSON. Only kicks in when an
                    # output schema is configured.
                    has_schema = python_cfg.output_schema_path or isinstance(
                        agent.__dict__.get("_composed_schema"), dict
                    )
                    if has_schema:
                        output = self._maybe_load_output_file(output, workdir)

                    # --- Error recovery (any failure including timeout) ---
                    if not final_ok:
                        if error_retries_left > 0:
                            error_retries_left -= 1
                            reason = (
                                "timeout"
                                if final_status == RunStatus.TIMEOUT.value
                                else "run_error"
                            )
                            current_input = self._build_error_retry_prompt(
                                input_, output, final_error
                            )
                            session.emit_retry(
                                attempt=attempt + 1,
                                reason=reason,
                                error=final_error,
                            )
                            session.emit_log(
                                level="warn",
                                message=(
                                    f"Run failed (attempt {attempt + 1}): "
                                    f"{final_error} — retrying "
                                    f"({error_retries_left} left)"
                                ),
                            )
                            continue
                        # No retries left — final error is already set.
                        break

                    # --- Validation retry (output schema check) -----------
                    if has_schema:
                        result = adapter.validate_output(
                            agent,
                            workdir,
                            output,
                            project_root=self.settings.project_root,
                        )
                        schema_validated_via = result.engine
                        mode = getattr(agent, "_composed_validation_mode", "strict")
                        session.emit_validation(
                            ok=result.ok,
                            attempt=attempt + 1,
                            mode=mode,
                            engine=result.engine,
                            error=None if result.ok else result.error,
                        )
                        if result.ok:
                            validation_status = "ok"
                            validation_errors = None
                            break
                        validation_status = "fail"
                        validation_errors = [result.error]
                        if validation_retries_left > 0:
                            validation_retries_left -= 1
                            current_input = self._build_retry_prompt(
                                input_, output, result.error
                            )
                            session.emit_retry(
                                attempt=attempt + 1,
                                reason="validation_failed",
                                error=result.error,
                            )
                            session.emit_log(
                                level="warn",
                                message=(
                                    f"Validation failed (attempt {attempt + 1}): "
                                    f"{result.error} — retrying "
                                    f"({validation_retries_left} left)"
                                ),
                            )
                            continue
                        # Final attempt failed validation
                        if mode == "strict":
                            final_ok = False
                            final_error = f"output validation failed: {result.error}"
                            # Validation failure is an expected, agent-level
                            # outcome — classify as ``failed`` so the
                            # error-status bucket stays reserved for
                            # unexpected runner crashes.
                            final_status = RunStatus.FAILED.value
                        elif mode == "warn":
                            validation_status = "warn"
                        break

                    # Success path — no validation configured or passed.
                    break

                try:
                    await self._run_guardrails(
                        run_id, agent, input_, output or "", session
                    )
                except Exception as exc:
                    suffix = f"guardrail error: {exc}"
                    final_error = (
                        f"{final_error} | {suffix}" if final_error else suffix
                    )
                if schema_validated_via is None:
                    mode = getattr(agent, "_composed_validation_mode", "strict")
                    if mode == "off":
                        schema_validated_via = "off"
                # Reclassify expected, agent-level failures (rate-limit /
                # connection / auth / validation) from ``error`` → ``failed``.
                # Leaves ``timeout`` and any already-set status alone.
                if not final_ok and final_status is None:
                    final_status = _classify_terminal_error(final_error)

                # ALWAYS emit the terminal DoneEvent through the session so
                # it lands last in both the transcript and WS stream. The
                # backend's own DoneEvent was captured (not re-emitted)
                # above, so this is the only ``done`` clients see.
                if not session.done_emitted:
                    session.emit_done(
                        ok=bool(final_ok),
                        error=final_error,
                        status=final_status,
                    )
        finally:
            # Re-persist conversation_uri for runners that discover
            # their session ID during execution (e.g. OpenCode).
            conv_meth = getattr(adapter, "conversation_uri", None)
            if conv_meth is not None:
                post_uri = conv_meth(
                    run_id=run_id, transcript_path=str(transcript_path)
                )
                if post_uri:
                    self.store.set_run_conversation(
                        run_id,
                        conversation_format=None,
                        conversation_uri=post_uri,
                    )
            self.store.finish_run(
                run_id,
                ok=final_ok,
                output=output,
                error=final_error,
                status=final_status,
                validation_status=validation_status,
                validation_errors=validation_errors,
                schema_validated_via=schema_validated_via,
            )
            try:
                refreshed = self.store.get_run(run_id)
                if refreshed is not None:
                    schedule_webhook(agent, refreshed, self.store, broadcaster, transcript_path)
            except Exception:
                pass
            with contextlib.suppress(Exception):
                broadcaster.close()
            with contextlib.suppress(Exception):
                self._cleanup_run_dir(run_dir)
            with contextlib.suppress(Exception):
                self._cleanup_workdir(agent, workdir)

    @staticmethod
    def _maybe_load_output_file(current: str | None, workdir: Path) -> str | None:
        """Return ``workdir/output.json`` content when ``current`` isn't JSON.

        Agents occasionally write their structured output to disk instead
        of inlining it. If the runner's text output doesn't parse as JSON
        and an ``output.json`` file exists in the workdir, swap it in so
        validation can engage on the file content. Falls back to
        ``current`` on any IO/decode failure.
        """
        if current:
            try:
                json.loads(extract_json(current))
                return current
            except (json.JSONDecodeError, ValueError):
                pass
        candidate = workdir / "output.json"
        try:
            if candidate.is_file():
                content = candidate.read_text(encoding="utf-8").strip()
                if content:
                    return content
        except OSError:
            pass
        return current

    @staticmethod
    def _build_retry_prompt(
        original_input: str, previous_output: str, validation_error: str
    ) -> str:
        return (
            f"{original_input}\n\n"
            f"--- PREVIOUS ATTEMPT FAILED VALIDATION ---\n"
            f"Your previous output did not pass validation:\n\n"
            f"{validation_error}\n\n"
            f"--- YOUR PREVIOUS OUTPUT ---\n"
            f"{previous_output}\n\n"
            f"--- FIX IT ---\n"
            f"Fix the issues above and produce a corrected output that passes validation."
        )

    @staticmethod
    def _build_error_retry_prompt(
        original_input: str, previous_output: str | None, error: str | None
    ) -> str:
        parts = [
            f"{original_input}\n\n",
            "--- PREVIOUS ATTEMPT FAILED ---\n",
        ]
        if error:
            parts.append(f"The run failed with the following error:\n\n{error}\n\n")
        if previous_output:
            parts.append(f"--- YOUR PREVIOUS OUTPUT ---\n{previous_output}\n\n")
        parts.append(
            "--- FIX IT ---\n"
            "Review the error above, correct the issue, and produce a new output."
        )
        return "".join(parts)

    async def _run_guardrails(
        self,
        run_id: str,
        agent: AgentDef,
        input_: str,
        output: str,
        session: RunStreamSession,
    ) -> None:
        for idx, ref in enumerate(agent.guardrails):
            try:
                cls = get_guardrail(ref.name)
            except KeyError as exc:
                session.emit(
                    GuardrailEvent(
                        run_id=run_id, name=ref.name, ok=False, message=str(exc)
                    )
                )
                continue
            instance = cls()
            ctx = GuardrailContext(
                run_id=run_id,
                agent_id=agent.id,
                input=input_,
                output=output,
                transcript_path=str(session.transcript_path),
                attempt=idx,
                options=ref.options,
            )
            result = instance.evaluate(ctx)
            self.store.record_guardrail(
                run_id, ref.name, result.ok, result.message, attempt=idx
            )
            session.emit(
                GuardrailEvent(
                    run_id=run_id,
                    name=ref.name,
                    ok=result.ok,
                    message=result.message,
                    attempt=idx,
                )
            )

    def _stamp_run_agent_version(self, run_id: str, agent: AgentDef) -> None:
        try:
            status = check_drift(agent, self.store)
            # Run the sweep on drift OR always sync prompt content so
            # out-of-band prompt edits get versioned even when the agent
            # definition is unchanged.
            if status in ("drifted", "new"):
                startup_sweep(
                    [agent], self.store, project_root=self.settings.project_root
                )
            else:
                from agentbox.core.versioning.drift import _sync_prompt

                _sync_prompt(agent, self.store, self.settings.project_root)
            latest = self.store.latest_version(agent.id)
            if latest is not None:
                with self.store.engine.begin() as conn:
                    conn.execute(
                        _runs_table.update()
                        .where(_runs_table.c.id == run_id)
                        .values(agent_version_id=latest["id"])
                    )
        except Exception:
            logger.exception("failed to stamp agent version for run %s", run_id)

    def _cleanup_workdir(self, agent: AgentDef, workdir: Path) -> None:
        if agent.workspace != "<ephemeral>":
            return
        if agent.session_mode == "persistent":
            return
        with contextlib.suppress(OSError):
            shutil.rmtree(workdir.parent, ignore_errors=True)


__all__ = ["RunBroadcaster", "RunExecutor"]
