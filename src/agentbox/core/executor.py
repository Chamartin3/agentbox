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
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.api.events import (
    DoneEvent,
    GuardrailEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    UsageEvent,
)
from agentbox.api.webhooks import schedule_webhook
from agentbox.config import Settings
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.config_generation import ConfigGenerator
from agentbox.core.data import SessionStore
from agentbox.core.data.schema import runs as _runs_table
from agentbox.core.definitions import AgentDef, DefinitionLoader
from agentbox.core.guardrails.base import GuardrailContext
from agentbox.core.plugins import get_backend, get_guardrail
from agentbox.core.prompt_capture import build_fragments, fragments_to_json
from agentbox.core.render import materialize_rendered_config
from agentbox.core.runners.base import RunRequest
from agentbox.core.versioning.drift import check_drift, startup_sweep
from agentbox.core.workspaces import (
    load_capabilities,
    resolve_path,
)

try:
    import jsonschema as _jsonschema
except ImportError:
    _jsonschema = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from agentbox.core.backends.base import BackendAdapter
    from agentbox.core.mcp.registry import McpRegistry

logger = logging.getLogger(__name__)


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


class _LegacyRunnerAdapter:
    """Wraps a legacy ``Runner`` subclass so it satisfies the
    ``BackendAdapter`` protocol (has ``render()`` + ``run()``).

    ``render()`` produces a minimal ``RenderedConfig`` with agent metadata
    encoded in ``agent_meta`` so ``run()`` can reconstruct the
    ``RunRequest`` the legacy runner expects.
    """

    name = "_legacy"

    def __init__(self, runner: Any, agent: AgentDef, project_root: Path):
        self._runner = runner
        self._agent = agent
        self._project_root = project_root

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: list[Any] | None = None,
        creds: dict[str, str] | None = None,
    ) -> RenderedConfig:
        files = {}
        claude_md = workdir / "CLAUDE.md"
        if claude_md.exists():
            files["CLAUDE.md"] = claude_md.read_bytes()
        return RenderedConfig(
            files=files,
            cwd=Path("."),
            agent_meta={
                "agent_id": agent.id,
                "project_root": str(self._project_root),
            },
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        req = RunRequest(
            run_id=run_id,
            agent=self._agent,
            input=input,
            workdir=rendered.cwd,
            project_root=self._project_root,
        )
        async for ev in self._runner.run(req):
            yield ev


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
    ) -> str:
        workdir, session_id = self._prepare_workdir(
            agent, session_id, workspace_override
        )

        agent = self._apply_overrides(
            agent, timeout_seconds, webhook_url, runner_override
        )

        # --- composition path ------------------------------------------------
        composed_result = None
        if agent.composition is not None and variables is not None:
            from agentbox.core.composition.loader import load_bundle

            manifest = self.loader.load()
            shared_roots = {
                k: self.settings.project_root / v
                for k, v in (manifest.shared_assets or {}).items()
            }

            # Find the agent bundle path
            bundle_path = self._resolve_bundle_path(agent)
            bundle = load_bundle(
                agent_id=agent.id,
                root=bundle_path,
                manifest_composition=agent.composition,
                legacy_prompt_path=agent.prompt_path,
            )
            composed_result = bundle.compose(variables, shared_roots)
            # Attach composed metadata so backend adapters can read it
            agent = agent.model_copy(deep=True)
            agent.__dict__["_composed_system"] = composed_result.system
            agent.__dict__["_composed_user"] = composed_result.user
            agent.__dict__["_composed_schema"] = composed_result.schema
            agent.__dict__["_composed_bundle_sha"] = composed_result.bundle_sha
            input_ = composed_result.user

            # Wire output schema into runner spec for the executor's retry loop
            comp = agent.composition
            if comp and comp.output_schema and comp.output_validation != "off":
                schema_path = bundle_path / comp.output_schema
                runner_updates: dict = {
                    "output_schema_path": str(schema_path),
                }
                if comp.output_validation == "warn":
                    runner_updates["max_validation_retries"] = 0
                agent = agent.model_copy(
                    update={"runner": agent.runner.model_copy(update=runner_updates)}
                )
            agent.__dict__["_composed_validation_mode"] = (
                comp.output_validation if comp else "strict"
            )

        # Select backend adapter and render into run dir
        adapter, rendered = self._select_backend(agent, workdir, backend)
        rendered, run_dir = self._render_for_run(adapter, agent, workdir, rendered)

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
        )

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
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return run_id

    def _resolve_bundle_path(self, agent: AgentDef) -> Path:
        """Resolve the filesystem path for an agent's bundle."""
        if agent.source_path and agent.source_path.is_dir():
            return agent.source_path
        if agent.source_path and agent.source_path.is_file():
            return agent.source_path.parent
        # Fallback: agents_dir / agent.id
        return self.settings.project_root / "agents" / agent.id

    def _select_backend(
        self,
        agent: AgentDef,
        workdir: Path,
        backend_override: str | None = None,
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
            # Legacy Runner subclasses don't have render() — wrap them.
            if not hasattr(inst, "render"):
                inst = _LegacyRunnerAdapter(inst, agent, self.settings.project_root)
            return inst  # type: ignore[return-value]

        candidates: list[str] = []

        if backend_override:
            candidates = [backend_override]
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
                rendered = adapter.render(agent, workdir)
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
            ),
            run_dir,
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
        max_attempts = 1 + (agent.runner.max_validation_retries or 0)
        current_input = input_

        output_text: list[str] = []
        final_ok = False
        final_error: str | None = None
        final_status: str | None = None
        output: str | None = None
        validation_status: str | None = None
        validation_errors: list[str] | None = None

        timeout = agent.runner.timeout_seconds
        try:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(max_attempts):
                output_text.clear()

                with transcript_path.open("a", encoding="utf-8") as tf:
                    try:
                        async with asyncio.timeout(timeout):
                            async for ev in adapter.run(rendered, current_input, run_id):
                                self._handle_event(run_id, ev, output_text, tf)
                                broadcaster.publish(ev)
                                if isinstance(ev, DoneEvent):
                                    final_ok = ev.ok
                                    final_error = ev.error
                                    final_status = ev.status
                    except TimeoutError:
                        final_error = f"timeout after {timeout}s"
                        final_ok = False
                        final_status = "timeout"
                    except Exception as exc:
                        final_error = f"executor error: {type(exc).__name__}: {exc}"
                        final_ok = False

                output = "\n".join(output_text).strip() or None
                if not final_ok:
                    break

                if agent.runner.output_schema_path and output:
                    is_valid, v_error = self._validate_output(output, agent, workdir)
                    if is_valid:
                        validation_status = "ok"
                        validation_errors = None
                        break
                    validation_status = "fail"
                    validation_errors = [v_error]
                    if attempt < max_attempts - 1:
                        current_input = self._build_retry_prompt(
                            input_, output, v_error
                        )
                        broadcaster.publish(
                            LogEvent(
                                run_id=run_id,
                                level="warn",
                                message=(
                                    f"Validation failed (attempt {attempt + 1}): "
                                    f"{v_error} — retrying"
                                ),
                            )
                        )
                        continue
                    # Final attempt failed validation
                    mode = getattr(agent, "_composed_validation_mode", "strict")
                    if mode == "strict":
                        final_ok = False
                        final_error = f"output validation failed: {v_error}"
                    elif mode == "warn":
                        validation_status = "warn"
                    break

                break
            try:
                await self._run_guardrails(
                    run_id, agent, input_, output or "", transcript_path, broadcaster
                )
            except Exception as exc:
                suffix = f"guardrail error: {exc}"
                final_error = f"{final_error} | {suffix}" if final_error else suffix
        finally:
            self.store.finish_run(
                run_id,
                ok=final_ok,
                output=output,
                error=final_error,
                status=final_status,
                validation_status=validation_status,
                validation_errors=validation_errors,
            )
            try:
                refreshed = self.store.get_run(run_id)
                if refreshed is not None:
                    schedule_webhook(agent, refreshed, self.store)
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
            output_text.append(ev.text)
        elif isinstance(ev, UsageEvent):
            self.store.record_usage(run_id, ev.model_dump())

    def _validate_output(
        self, output: str, agent: AgentDef, workdir: Path
    ) -> tuple[bool, str]:
        if not agent.runner.output_schema_path:
            return True, ""

        schema_path = workdir / agent.runner.output_schema_path
        if not schema_path.exists():
            schema_path = self.settings.project_root / agent.runner.output_schema_path
        if not schema_path.exists():
            return False, f"schema file not found: {agent.runner.output_schema_path}"

        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return False, f"cannot load schema: {exc}"

        try:
            instance = json.loads(output)
        except json.JSONDecodeError as exc:
            return False, f"output is not valid JSON: {exc}"

        if _jsonschema is None:
            return self._basic_shape_check(instance, schema)
        try:
            _jsonschema.validate(instance=instance, schema=schema)
            return True, ""
        except _jsonschema.ValidationError as exc:
            return False, str(exc)

    @staticmethod
    def _basic_shape_check(instance: dict, schema: dict) -> tuple[bool, str]:
        props = schema.get("properties", {})
        required = schema.get("required", [])

        for field in required:
            if field not in instance:
                return False, f"missing required field: {field}"
            field_schema = props.get(field, {})
            expected_type = field_schema.get("type")
            if expected_type:
                type_map = {
                    "string": str,
                    "integer": int,
                    "number": (int, float),
                    "boolean": bool,
                    "object": dict,
                    "array": list,
                }
                py_type = type_map.get(expected_type)
                if py_type and not isinstance(instance[field], py_type):
                    return (
                        False,
                        f"field {field!r}: expected {expected_type}, "
                        f"got {type(instance[field]).__name__}",
                    )
            if isinstance(instance[field], str):
                min_len = field_schema.get("minLength")
                max_len = field_schema.get("maxLength")
                val = instance[field]
                if min_len is not None and len(val) < min_len:
                    return (
                        False,
                        f"field {field!r}: min length {min_len}, got {len(val)}",
                    )
                if max_len is not None and len(val) > max_len:
                    return (
                        False,
                        f"field {field!r}: max length {max_len}, got {len(val)}",
                    )
            enum_vals = field_schema.get("enum")
            if enum_vals and instance[field] not in enum_vals:
                return (
                    False,
                    f"field {field!r}: must be one of {enum_vals}, "
                    f"got {instance[field]!r}",
                )

        return True, ""

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
                broadcaster.publish(
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
                transcript_path=str(transcript_path),
                attempt=idx,
                options=ref.options,
            )
            result = instance.evaluate(ctx)
            self.store.record_guardrail(
                run_id, ref.name, result.ok, result.message, attempt=idx
            )
            broadcaster.publish(
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
            if status in ("drifted", "new"):
                startup_sweep([agent], self.store)
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
