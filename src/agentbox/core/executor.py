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
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema as _jsonschema

from agentbox.api.events import (
    DoneEvent,
    GuardrailEvent,
    LogEvent,
    RetryEvent,
    RunEvent,
    TextEvent,
    TimeoutEvent,
    UsageEvent,
    ValidationEvent,
)
from agentbox.api.webhooks import schedule_webhook
from agentbox.config import Settings
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.config_generation import ConfigGenerator
from agentbox.core.constants import RunStatus
from agentbox.core.data import SessionStore
from agentbox.core.data.schema import runs as _runs_table
from agentbox.core.definitions import AgentDef, DefinitionLoader
from agentbox.core.guardrails.base import GuardrailContext
from agentbox.core.host_env.capabilities import CAPABILITIES as _HOST_ENV_CAPABILITIES
from agentbox.core.plugins import get_backend, get_guardrail
from agentbox.core.prompt_capture import build_fragments, fragments_to_json
from agentbox.core.render import materialize_rendered_config
from agentbox.core.resources.prompt_resolver import resolve_prompt
from agentbox.core.resources.workspace_materialize import materialize_workspace
from agentbox.core.run_prep import (
    prompt_resolution_to_snapshot,
    render_env_doc,
    resolve_agent_prompt_bindings,
    resolve_workspace_resources,
    workspace_outcomes_to_snapshot,
)
from agentbox.core.runner_profiles import (
    EffectiveRunnerConfig,
    RunnerProfileResolver,
)
from agentbox.core.streaming.rate_limit import detect_in_text_line
from agentbox.core.versioning.drift import check_drift, startup_sweep
from agentbox.core.workspaces import (
    load_capabilities,
    resolve_path,
)

if TYPE_CHECKING:
    from agentbox.core.backends.base import BackendAdapter
    from agentbox.core.mcp.registry import McpRegistry

logger = logging.getLogger(__name__)


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Pull a JSON payload out of model output that may include prose / fences.

    Models often wrap the JSON in ```json fences and surrounding prose
    despite being told not to. Validation should still engage on the JSON
    they produced, so we extract the first fenced block when present;
    otherwise we fall back to the first '{...}' / '[...]' slice; otherwise
    return the raw text unchanged for json.loads to fail on naturally.
    """
    if not text:
        return text
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith(("{", "[")):
        return s
    for opener, closer in (("{", "}"), ("[", "]")):
        i = s.find(opener)
        j = s.rfind(closer)
        if 0 <= i < j:
            return s[i : j + 1]
    return s


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


def _format_validation_error(exc: _jsonschema.ValidationError) -> str:
    """Render a jsonschema ValidationError so the agent sees *where* it failed.

    The default ``str(exc)`` dumps the schema and instance but does not say
    *which JSON pointer path* in the instance the failing validator was
    anchored at — so when ``oneOf`` is at the root, agents often think it's
    anchored on a nested object and fix the wrong place.
    """
    instance_pointer = "/" + "/".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "/"
    schema_pointer = "/" + "/".join(str(p) for p in exc.absolute_schema_path) if exc.absolute_schema_path else "/"
    lines = [
        f"validation failed at instance path: {instance_pointer}",
        f"schema rule violated at: {schema_pointer} ({exc.validator})",
        f"message: {exc.message}",
    ]
    if exc.validator == "oneOf" and exc.context:
        lines.append("")
        lines.append("oneOf sub-errors (each branch's first failure):")
        for branch_idx, sub in enumerate(exc.context):
            title = ""
            try:
                title = sub.schema.get("title", "") if isinstance(sub.schema, dict) else ""
            except AttributeError:
                title = ""
            label = f"branch[{branch_idx}]"
            if title:
                label += f" ({title})"
            sub_path = "/" + "/".join(str(p) for p in sub.absolute_path) if sub.absolute_path else "/"
            lines.append(f"  - {label} at {sub_path}: {sub.message}")
    try:
        instance_preview = json.dumps(exc.instance, default=str)
    except (TypeError, ValueError):
        instance_preview = repr(exc.instance)
    if len(instance_preview) > 800:
        instance_preview = instance_preview[:800] + "...(truncated)"
    lines.append("")
    lines.append(f"failing instance ({instance_pointer}): {instance_preview}")
    return "\n".join(lines)


def _load_workspace_permissions(
    workdir: Path, agent: AgentDef, loader: DefinitionLoader, settings: Settings
) -> dict:
    """Load workspace permissions from WorkspaceDef or capabilities.json (deprecated).

    Resolution order:
    1. Try to resolve the agent's workspace and get permissions from WorkspaceDef.
    2. Fall back to loading from capabilities.json (deprecated).
    """
    try:
        # Try to get WorkspaceDef first
        if agent.workspace:
            if agent.workspace == "<ephemeral>":
                return {}
            ws_def = loader.get_workspace(agent.workspace)
            if ws_def is not None:
                return {
                    "allowed_tools": ws_def.allowed_tools,
                    "allowed_builtin_tools": ws_def.allowed_builtin_tools,
                    "files": [f.model_dump() for f in ws_def.files],
                    "max_tokens": ws_def.max_tokens,
                    "allow_file_write": ws_def.allow_file_write,
                    "allow_network": ws_def.allow_network,
                }
        # Fall back to loading from JSON (deprecated)
        return load_capabilities(workdir)
    except Exception:
        return {}


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

        agent = self._apply_overrides(
            agent, timeout_seconds, webhook_url, runner_override
        )

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

        # --- composition path ------------------------------------------------
        composed_result = None
        bundle_path: Path | None = None
        if agent.composition is not None and variables is not None:
            from agentbox.core.composition.loader import (
                load_bundle,
                load_bundle_from_db,
            )

            manifest = self.loader.load()
            shared_roots = {
                k: self.settings.project_root / v
                for k, v in (manifest.shared_assets or {}).items()
            }

            # Find the agent bundle path
            bundle_path = self._resolve_bundle_path(agent)

            # DB-first composition: when the active version has captured
            # files, render from the snapshot. ``AGENTBOX_BUNDLE_SOURCE=disk``
            # forces the legacy filesystem path (useful for debugging a
            # mismatch between DB content and disk).
            bundle = None
            source_pref = os.getenv("AGENTBOX_BUNDLE_SOURCE", "auto").lower()
            if source_pref != "disk":
                try:
                    active = self.store.get_active_version(agent.id)
                    if active is not None:
                        files = self.store.list_version_files(active["id"])
                        if files:
                            bundle = load_bundle_from_db(
                                agent_id=agent.id,
                                composition=agent.composition,
                                files=files,
                                fallback_path=bundle_path,
                            )
                except Exception:
                    logger.exception(
                        "executor: DB bundle load failed for %r — falling back to disk",
                        agent.id,
                    )
                    bundle = None
            if bundle is None:
                bundle = load_bundle(
                    agent_id=agent.id,
                    root=bundle_path,
                    manifest_composition=agent.composition,
                    legacy_prompt_path=agent.prompt_path,
                )
            composed_result = bundle.compose(variables, shared_roots)

            # Append validation-engine hint to system prompt when a schema
            # is present so the LLM knows how strictly its output will be
            # checked.
            system_text = composed_result.system
            if composed_result.schema is not None:
                engine = getattr(
                    agent.runner, "output_validation_engine", "both"
                )
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
            if bundle_path is None:
                bundle_path = self._resolve_bundle_path(agent)
            if composed_result is None:
                agent = agent.model_copy(deep=True)
            schema_rel: str | None = None
            if comp.output_schema:
                schema_rel = comp.output_schema
            else:
                from agentbox.core.constants import BundleFile

                for fallback in (
                    BundleFile.OUTPUT_SCHEMA,
                    BundleFile.OUTPUT_SCHEMA_ALT,
                ):
                    if (bundle_path / fallback).exists():
                        schema_rel = fallback
                        break
            if schema_rel and comp.output_validation != "off":
                schema_path = bundle_path / schema_rel
                runner_updates: dict = {
                    "output_schema_path": str(schema_path),
                }
                if comp.output_validation == "warn":
                    runner_updates["max_validation_retries"] = 0
                agent = agent.model_copy(
                    update={"runner": agent.runner.model_copy(update=runner_updates)}
                )
            agent.__dict__["_composed_validation_mode"] = comp.output_validation

        # --- prompt resource binding substitution (Plan 08 Phase 1) ----------
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

        if effective.source in ("agent_legacy", "backend_default"):
            error_msg = (
                f"agent {agent.id!r} has no runner profile bound. "
                "Assign a runner profile in the UI (Agents → Runner Profile)."
            )
            return self._fail_pre_run(agent, input_, workdir, session_id, error_msg)

        # Apply effective timeout if not already overridden
        effective_timeout = timeout_seconds or effective.timeout_seconds
        if effective_timeout and not timeout_seconds:
            agent = self._apply_overrides(
                agent, effective_timeout, webhook_url, runner_override
            )

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

        # Record the effective model immediately at run creation — before
        # the runner task starts — so every run has a model name in the
        # usage table regardless of backend, status, or whether the
        # runner ever emits a UsageEvent. ``rendered.model`` is populated
        # by the adapter's ``render()`` (spec.model or backend default).
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
            )
        )
        self._tasks.add(task)

        def _on_task_done(t: asyncio.Task[None]) -> None:
            self._tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    logger.exception(
                        "run task crashed", exc_info=(type(exc), exc, exc.__traceback__)
                    )

        task.add_done_callback(_on_task_done)
        return run_id

    def _resolve_bundle_path(self, agent: AgentDef) -> Path:
        """Resolve the filesystem path for an agent's bundle."""
        if agent.source_path and agent.source_path.is_dir():
            return agent.source_path
        if agent.source_path and agent.source_path.is_file():
            return agent.source_path.parent
        # Fallback: agents_dir / agent.id
        return self.settings.project_root / "agents" / agent.id

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
        2. ``backend_preference`` list from the project manifest; skip any
           in ``agent.unsupported_backends``.
        3. Fall back to ``agent.runner.kind`` (deprecated).
        4. ``NO_BACKEND_AVAILABLE`` error.
        """
        manifest = self.loader.load()

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
        elif manifest.backend_preference:
            candidates = [
                n
                for n in manifest.backend_preference
                if n not in agent.unsupported_backends
            ]
        else:
            kind = agent.runner.kind
            if kind is not None:
                candidates = [str(kind)]

        for name in candidates:
            adapter = _try_backend(name)
            if adapter is not None:
                rendered = adapter.render(
                    agent, workdir, runner_config=runner_config
                )
                return adapter, rendered

        raise KeyError("NO_BACKEND_AVAILABLE")

    @staticmethod
    def _apply_overrides(
        agent: AgentDef,
        timeout_seconds: int | None,
        webhook_url: str | None,
        runner_override: str | None = None,
    ) -> AgentDef:
        runner_updates: dict = {}
        if timeout_seconds is not None:
            runner_updates["timeout_seconds"] = timeout_seconds
        if runner_override is not None:
            runner_updates["kind"] = runner_override

        kwargs: dict = {}
        if runner_updates:
            kwargs["runner"] = agent.runner.model_copy(update=runner_updates)
        if webhook_url is not None:
            kwargs["webhook_url"] = webhook_url
        if kwargs:
            return agent.model_copy(update=kwargs)
        return agent

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
            workdir, agent, self.loader, self.settings
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
    ) -> None:
        current_input = input_

        output_text: list[str] = []
        final_ok = False
        final_error: str | None = None
        final_status: str | None = None
        done_event_published = False
        output: str | None = None
        validation_status: str | None = None
        validation_errors: list[str] | None = None
        schema_validated_via: str | None = None

        error_retries_left = agent.runner.max_error_retries or 0
        validation_retries_left = agent.runner.max_validation_retries or 0
        # Cap total attempts to avoid infinite loops.
        max_attempts = 1 + error_retries_left + validation_retries_left

        timeout = agent.runner.timeout_seconds
        try:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            # Model is pre-recorded at run creation (see ``execute``); no
            # need to re-record here. UsageEvents from the runner refine
            # token/cost; model is preserved by COALESCE in record_usage.
            for attempt in range(max_attempts):
                output_text.clear()
                run_error: str | None = None

                with transcript_path.open("a", encoding="utf-8", buffering=1) as tf:
                    try:
                        async with asyncio.timeout(timeout):
                            async for ev in adapter.run(rendered, current_input, run_id):
                                self._handle_event(run_id, ev, output_text, tf)
                                broadcaster.publish(ev)
                                if isinstance(ev, DoneEvent):
                                    final_ok = ev.ok
                                    final_error = ev.error
                                    final_status = ev.status
                                    done_event_published = True
                                    # Finalize as soon as the runner signals done;
                                    # don't wait for the generator to drain. Any
                                    # tail-end task can otherwise delay or skip
                                    # the finally block (status persist + webhook).
                                    break
                                # Centralised fatal-pattern detection: any
                                # LogEvent whose message matches a known
                                # rate-limit / auth / quota signature aborts
                                # the run immediately instead of waiting for
                                # the per-run timeout. Applies to every
                                # backend that surfaces diagnostics as
                                # LogEvents — no per-runner duplication.
                                if isinstance(ev, LogEvent):
                                    fatal = detect_in_text_line(ev.message or "")
                                    if fatal is not None:
                                        final_ok = False
                                        final_error = fatal
                                        final_status = RunStatus.FAILED.value
                                        break
                    except TimeoutError:
                        run_error = f"timeout after {timeout}s"
                        final_error = run_error
                        final_ok = False
                        final_status = RunStatus.TIMEOUT.value
                        if timeout is not None:
                            to_ev = TimeoutEvent(
                                run_id=run_id,
                                timeout_seconds=timeout,
                                error=run_error,
                            )
                            tf.write(to_ev.model_dump_json() + "\n")
                            broadcaster.publish(to_ev)
                    except Exception as exc:
                        import traceback as _tb
                        tb_text = _tb.format_exc()
                        run_error = f"executor error: {type(exc).__name__}: {exc}\n{tb_text}"
                        final_error = run_error
                        final_ok = False
                        logging.getLogger("agentbox.executor").exception(
                            "runner crashed for run %s", run_id
                        )

                    # --- Post-run logic (inside with block so tf is available) ---
                    if run_error:
                        ev = LogEvent(
                            run_id=run_id,
                            level="error",
                            message=run_error,
                        )
                        tf.write(ev.model_dump_json() + "\n")
                        broadcaster.publish(ev)

                    output = "\n".join(output_text).strip() or None

                    # --- workdir/output.json fallback ---------------------------
                    # When the agent wrote its structured output to a file
                    # instead of returning it inline (e.g. opencode running
                    # with write tools), prefer the file content if the text
                    # output doesn't parse as JSON. Only kicks in when an
                    # output schema is configured.
                    if agent.runner.output_schema_path:
                        output = self._maybe_load_output_file(output, workdir)

                    # --- Error recovery (any failure including timeout) ----------
                    if not final_ok:
                        if error_retries_left > 0:
                            error_retries_left -= 1
                            reason = "timeout" if final_status == RunStatus.TIMEOUT.value else "run_error"
                            current_input = self._build_error_retry_prompt(
                                input_, output, final_error
                            )
                            ev = RetryEvent(
                                run_id=run_id,
                                attempt=attempt + 1,
                                reason=reason,
                                error=final_error,
                            )
                            tf.write(ev.model_dump_json() + "\n")
                            broadcaster.publish(ev)
                            ev = LogEvent(
                                run_id=run_id,
                                level="warn",
                                message=(
                                    f"Run failed (attempt {attempt + 1}): {final_error} — "
                                    f"retrying ({error_retries_left} left)"
                                ),
                            )
                            tf.write(ev.model_dump_json() + "\n")
                            broadcaster.publish(ev)
                            continue
                        # No retries left — final error is already set.
                        break

                    # --- Validation retry (output schema check) -----------------
                    if agent.runner.output_schema_path:
                        if not output:
                            is_valid = False
                            v_error = "output is empty but an output schema is required"
                            schema_validated_via = "none"
                        else:
                            is_valid, v_error, schema_validated_via = (
                                self._validate_output(output, agent, workdir)
                            )
                        mode = getattr(agent, "_composed_validation_mode", "strict")
                        engine = schema_validated_via or "none"
                        v_ev = ValidationEvent(
                            run_id=run_id,
                            ok=is_valid,
                            attempt=attempt + 1,
                            mode=mode if mode in ("strict", "warn", "off") else "strict",
                            engine=engine if engine in ("jsonschema", "pydantic", "both", "none") else "none",
                            error=None if is_valid else v_error,
                        )
                        tf.write(v_ev.model_dump_json() + "\n")
                        broadcaster.publish(v_ev)
                        if is_valid:
                            validation_status = "ok"
                            validation_errors = None
                            break
                        validation_status = "fail"
                        validation_errors = [v_error]
                        if validation_retries_left > 0:
                            validation_retries_left -= 1
                            current_input = self._build_retry_prompt(
                                input_, output, v_error
                            )
                            ev = RetryEvent(
                                run_id=run_id,
                                attempt=attempt + 1,
                                reason="validation_failed",
                                error=v_error,
                            )
                            tf.write(ev.model_dump_json() + "\n")
                            broadcaster.publish(ev)
                            ev = LogEvent(
                                run_id=run_id,
                                level="warn",
                                message=(
                                    f"Validation failed (attempt {attempt + 1}): "
                                    f"{v_error} — retrying ({validation_retries_left} left)"
                                ),
                            )
                            tf.write(ev.model_dump_json() + "\n")
                            broadcaster.publish(ev)
                            continue
                        # Final attempt failed validation
                        if mode == "strict":
                            final_ok = False
                            final_error = f"output validation failed: {v_error}"
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
                    run_id, agent, input_, output or "", transcript_path, broadcaster
                )
            except Exception as exc:
                suffix = f"guardrail error: {exc}"
                final_error = f"{final_error} | {suffix}" if final_error else suffix
            if schema_validated_via is None:
                mode = getattr(agent, "_composed_validation_mode", "strict")
                if mode == "off":
                    schema_validated_via = "off"
            # Reclassify expected, agent-level failures (rate-limit /
            # connection / auth / validation) from ``error`` → ``failed``.
            # Leaves ``timeout`` and any already-set status alone.
            if not final_ok and final_status is None:
                final_status = _classify_terminal_error(final_error)
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
            # Ensure WS clients always see a terminal DoneEvent. The
            # runner publishes its own DoneEvent on the happy path
            # (handled in the loop above), but when the executor breaks
            # out early on timeout / fatal-pattern detection / validation
            # failure / unexpected crash, no DoneEvent has been
            # broadcast — clients would hang waiting for one. Synthesize
            # one here so every terminal path emits exactly one DoneEvent.
            if not done_event_published:
                with contextlib.suppress(Exception):
                    final_done = DoneEvent(
                        run_id=run_id,
                        ok=bool(final_ok),
                        error=final_error,
                        status=final_status,
                    )
                    with transcript_path.open("a", encoding="utf-8", buffering=1) as _tf:
                        _tf.write(final_done.model_dump_json() + "\n")
                    broadcaster.publish(final_done)
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

    def _handle_event(
        self,
        run_id: str,
        ev: RunEvent,
        output_text: list[str],
        tf,
    ) -> None:
        tf.write(ev.model_dump_json() + "\n")
        if isinstance(ev, TextEvent):
            # Delta events are UI-only. Prompt turns should be persisted and
            # broadcast, but only assistant text is the run output.
            if (
                not getattr(ev, "delta", False)
                and getattr(ev, "role", "assistant") == "assistant"
            ):
                output_text.append(ev.text)
        elif isinstance(ev, UsageEvent):
            self.store.record_usage(run_id, ev.model_dump())

    def _validate_output(
        self, output: str, agent: AgentDef, workdir: Path
    ) -> tuple[bool, str, str]:
        """Validate *output* against the agent's output schema.

        Returns ``(is_valid, error_message, validated_via)`` where
        *validated_via* is ``"jsonschema"``, ``"pydantic"``, or
        ``"both"``.
        """
        # Composition pipeline attaches the parsed schema dict to the agent
        # as ``_composed_schema``. Prefer it over re-reading the file: it
        # works uniformly for disk-backed bundles and DB-only agents (which
        # have no on-disk schema file). Falls back to the legacy on-disk
        # path-based load when composition didn't run.
        composed_schema = agent.__dict__.get("_composed_schema")
        if isinstance(composed_schema, dict):
            schema = composed_schema
        else:
            if not agent.runner.output_schema_path:
                return True, "", "off"

            schema_path = workdir / agent.runner.output_schema_path
            if not schema_path.exists():
                schema_path = self.settings.project_root / agent.runner.output_schema_path
            if not schema_path.exists():
                return False, f"schema file not found: {agent.runner.output_schema_path}", "none"

            try:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                return False, f"cannot load schema: {exc}", "none"

        engine = getattr(agent.runner, "output_validation_engine", "both")

        if engine == "jsonschema":
            return self._validate_jsonschema(output, schema)

        if engine == "pydantic":
            return self._validate_pydantic(output, schema)

        # "both" — jsonschema first, then pydantic
        js_ok, js_err, _ = self._validate_jsonschema(output, schema)
        if not js_ok:
            return False, js_err, "jsonschema"
        py_ok, py_err, _ = self._validate_pydantic(output, schema)
        if not py_ok:
            return False, py_err, "pydantic"
        return True, "", "both"

    @staticmethod
    def _validate_jsonschema(
        output: str, schema: dict[str, Any]
    ) -> tuple[bool, str, str]:
        try:
            instance = json.loads(_extract_json(output))
        except json.JSONDecodeError as exc:
            return False, f"output is not valid JSON: {exc}", "jsonschema"
        try:
            _jsonschema.validate(instance=instance, schema=schema)
            return True, "", "jsonschema"
        except _jsonschema.ValidationError as exc:
            return False, _format_validation_error(exc), "jsonschema"

    @staticmethod
    def _validate_pydantic(
        output: str, schema: dict[str, Any]
    ) -> tuple[bool, str, str]:
        from agentbox.core.composition.pydantic_validate import validate_with_pydantic

        ok, err = validate_with_pydantic(output, schema)
        return ok, err, "pydantic"

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
                json.loads(_extract_json(current))
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
        transcript_path: Path,
        broadcaster: RunBroadcaster,
    ) -> None:
        for idx, ref in enumerate(agent.guardrails):
            try:
                cls = get_guardrail(ref.name)
            except KeyError as exc:
                ev = GuardrailEvent(
                    run_id=run_id, name=ref.name, ok=False, message=str(exc)
                )
                broadcaster.publish(ev)
                continue
            instance = cls()
            ctx = GuardrailContext(
                run_id=run_id,
                agent_id=agent.id,
                input=input_,
                output=output,
                transcript_path=str(transcript_path),
                attempt=idx,
                options=ref.options,
            )
            result = instance.evaluate(ctx)
            self.store.record_guardrail(
                run_id, ref.name, result.ok, result.message, attempt=idx
            )
            ev = GuardrailEvent(
                run_id=run_id,
                name=ref.name,
                ok=result.ok,
                message=result.message,
                attempt=idx,
            )
            broadcaster.publish(ev)
            try:
                with transcript_path.open("a", encoding="utf-8", buffering=1) as tf:
                    tf.write(ev.model_dump_json() + "\n")
            except OSError:
                pass

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
