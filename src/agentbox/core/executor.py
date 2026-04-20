"""RunExecutor — orchestrates a single agent run end-to-end.

Responsibilities:
- materialize a tmp or persistent workdir for the run
- instantiate the requested Runner plugin
- stream RunEvents into both an in-memory broadcast queue and the on-disk
  transcript JSONL
- aggregate usage events into the SessionStore
- validate output against JSON Schema and retry on failure
- invoke guardrails after completion
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import (
    DoneEvent,
    GuardrailEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    UsageEvent,
)
from agentbox.config import Settings
from agentbox.core.config_generation import ConfigGenerator
from agentbox.core.definitions import AgentDef, DefinitionLoader
from agentbox.core.guardrails.base import GuardrailContext
from agentbox.core.plugins import get_guardrail, get_runner
from agentbox.core.prompt_capture import build_fragments, fragments_to_json
from agentbox.core.runners.base import RunRequest
from agentbox.core.session_store import SessionStore
from agentbox.core.workspaces import (
    get_generated_paths,
    load_capabilities,
    resolve_path,
)


def _load_workspace_permissions(workdir: Path) -> dict:
    """Best-effort capabilities read for executor's pre-run config generation."""
    try:
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
    ):
        self.store = store
        self.settings = settings
        self.loader = loader
        self._broadcasters: dict[str, RunBroadcaster] = {}
        self._generator: ConfigGenerator | None = None

    @property
    def generator(self) -> ConfigGenerator:
        if self._generator is None:
            project_root = self.settings.project_root
            manifest = self.loader.load()
            agentbox_toml = project_root / "agentbox.toml"
            manifest_path = project_root / manifest.tool_manifest_path
            self._generator = ConfigGenerator(
                agentbox_toml=agentbox_toml,
                manifest_path=manifest_path,
                mcp_server_name=manifest.mcp_server_name,
                mcp_command=manifest.mcp_command,
                mcp_url=manifest.mcp_url,
                mcp_transport=manifest.mcp_transport,
                verbose=False,
            )
        return self._generator

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
    ) -> str:
        workdir, session_id = self._prepare_workdir(
            agent, session_id, workspace_override
        )
        # Ensure workspace configs are generated before the run.
        self._ensure_workspace_configs(workdir)

        # Apply per-run overrides to a copy of the agent.
        agent = self._apply_overrides(
            agent, timeout_seconds, webhook_url, runner_override
        )

        # Transcript lives outside the workdir so it survives headless cleanup.
        transcripts_dir = self.settings.data_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        import uuid as _uuid
        transcript_path = transcripts_dir / f"{_uuid.uuid4().hex}.jsonl"
        run_id = self.store.create_run(
            agent_id=agent.id,
            input_=input_,
            workdir=str(workdir),
            transcript_path=str(transcript_path),
            session_id=session_id,
        )
        broadcaster = RunBroadcaster()
        self._broadcasters[run_id] = broadcaster
        # Capture the assembled prompt fragments before the runner starts.
        try:
            frags = build_fragments(
                agent=agent,
                user_input=input_,
                project_root=self.settings.project_root,
                store=self.store,
            )
            self.store.save_run_prompt(run_id, fragments_to_json(frags))
        except Exception:  # noqa: BLE001 - capture is best-effort
            pass
        # Fire and forget — the WS endpoint subscribes; callers can also `await`.
        asyncio.create_task(
            self._run(run_id, agent, input_, workdir, transcript_path, broadcaster)
        )
        return run_id

    @staticmethod
    def _apply_overrides(
        agent: AgentDef,
        timeout_seconds: int | None,
        webhook_url: str | None,
        runner_override: str | None = None,
    ) -> AgentDef:
        """Return a copy of ``agent`` with per-run overrides applied."""
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
        # Workspace resolution with optional override.
        if workspace_override:
            # Temporarily swap workspace for resolution
            original = agent.workspace
            agent.workspace = workspace_override
            try:
                path, ephemeral = resolve_path(agent, self.settings, self.loader)
            finally:
                agent.workspace = original
            if not ephemeral:
                path.mkdir(parents=True, exist_ok=True)
                return path, session_id
            # If the override resolves to ephemeral, fall through to normal ephemeral handling

        # Normal resolution
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
        # headless ephemeral
        self.settings.runs_dir.mkdir(parents=True, exist_ok=True)
        wd = Path(tempfile.mkdtemp(prefix="run-", dir=self.settings.runs_dir)) / "workdir"
        wd.mkdir(parents=True, exist_ok=True)
        return wd, None

    def _ensure_workspace_configs(self, workdir: Path) -> None:
        """Generate runner configs for a workspace if they don't exist."""
        paths = get_generated_paths(workdir)
        if not paths["claude_agents"].exists():
            try:
                permissions = _load_workspace_permissions(workdir)
                self.generator.generate_for_workspace(
                    workdir,
                    allowed_builtin_tools=permissions.get("allowed_builtin_tools") or [],
                    files=permissions.get("files") or [],
                    project_root=self.settings.project_root,
                )
            except Exception:
                # Best-effort: don't block the run if generation fails.
                pass

    async def _run(
        self,
        run_id: str,
        agent: AgentDef,
        input_: str,
        workdir: Path,
        transcript_path: Path,
        broadcaster: RunBroadcaster,
    ) -> None:
        max_attempts = 1 + (agent.runner.max_validation_retries or 0)
        current_input = input_

        output_text: list[str] = []
        final_ok = False
        final_error: str | None = None
        output: str | None = None

        # finish_run must always run, otherwise the row stays as 'running'
        # forever (orphaned). Wrap everything below in try/finally — guardrail
        # bugs, cancellation, or unexpected exceptions must not strand the row.
        try:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(max_attempts):
                output_text.clear()
                runner_cls = get_runner(agent.runner.kind)
                runner = runner_cls()
                req = RunRequest(
                    run_id=run_id,
                    agent=agent,
                    input=current_input,
                    workdir=workdir,
                    project_root=self.settings.project_root,
                    session_id=None,
                )

                with transcript_path.open("a", encoding="utf-8") as tf:
                    try:
                        async for ev in runner.run(req):
                            self._handle_event(run_id, ev, output_text, tf)
                            broadcaster.publish(ev)
                            if isinstance(ev, DoneEvent):
                                final_ok = ev.ok
                                final_error = ev.error
                    except Exception as exc:  # noqa: BLE001 - surface to client
                        final_error = f"executor error: {exc}"
                        final_ok = False

                output = "\n".join(output_text).strip() or None

                # If the agent itself failed, stop retrying.
                if not final_ok:
                    break

                # Validate output against schema if configured.
                if (
                    attempt < max_attempts - 1
                    and agent.runner.output_schema_path
                    and output
                ):
                    is_valid, v_error = self._validate_output(
                        output, agent, workdir
                    )
                    if is_valid:
                        break
                    # Build retry prompt with the validation error.
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

                break  # No schema or last attempt
            try:
                await self._run_guardrails(
                    run_id, agent, input_, output or "", transcript_path, broadcaster
                )
            except Exception as exc:  # noqa: BLE001
                # Guardrail failures must not block the run from finishing.
                suffix = f"guardrail error: {exc}"
                final_error = f"{final_error} | {suffix}" if final_error else suffix
        finally:
            self.store.finish_run(
                run_id, ok=final_ok, output=output, error=final_error
            )
            try:
                from agentbox.api.webhooks import schedule_webhook

                refreshed = self.store.get_run(run_id)
                if refreshed is not None:
                    schedule_webhook(agent, refreshed, self.store)
            except Exception:  # noqa: BLE001
                # Webhook delivery is best-effort; never strand the run.
                pass
            try:
                broadcaster.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._cleanup_workdir(agent, workdir)
            except Exception:  # noqa: BLE001
                pass

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
        """Validate ``output`` against the agent's output JSON Schema.
        
        Returns ``(valid, error_message)``.
        """
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

        # Parse output as JSON first.
        try:
            instance = json.loads(output)
        except json.JSONDecodeError as exc:
            return False, f"output is not valid JSON: {exc}"

        # Validate using jsonschema if available, otherwise do basic shape check.
        try:
            import jsonschema

            jsonschema.validate(instance=instance, schema=schema)
            return True, ""
        except ImportError:
            # Basic shape check fallback.
            return self._basic_shape_check(instance, schema)
        except jsonschema.ValidationError as exc:
            return False, str(exc)

    @staticmethod
    def _basic_shape_check(instance: dict, schema: dict) -> tuple[bool, str]:
        """Minimal validation when ``jsonschema`` is not installed."""
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
            # Check string length constraints.
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
            # Check enum constraint.
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
        """Build a retry prompt that includes the original input, previous
        output, and validation error for the agent to fix."""
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
                    GuardrailEvent(run_id=run_id, name=ref.name, ok=False, message=str(exc))
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

    def _cleanup_workdir(self, agent: AgentDef, workdir: Path) -> None:
        # Workspaces are persistent unless explicitly ephemeral.
        if agent.workspace != "<ephemeral>":
            return
        if agent.session_mode == "persistent":
            return
        try:
            shutil.rmtree(workdir.parent, ignore_errors=True)
        except OSError:
            pass


__all__ = ["RunBroadcaster", "RunExecutor"]
