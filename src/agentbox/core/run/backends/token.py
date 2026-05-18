"""Unified ``token`` backend adapter — in-process LLM runner via pydantic-ai.

Merges the capabilities of the former ``pydantic_ai`` and
``pydantic_ai_structured`` backends into a single, canonical backend.

Two execution modes:

1. **Full-agent mode** — ``agent_module`` is set on the ``RunnerSpec``
   (e.g. ``agents.company_researcher.agent:CompanyResearcherAgent``).
   The backend imports the class, instantiates it with ``mcp_url=`` (and
   optional ``api_key``/``base_url``/``model`` kwargs for provider
   routing), and calls ``agent.run_sync(request)`` after validating the
   input against the agent's request model.

2. **Direct-agent mode** — no ``agent_module``.  A ``pydantic_ai.Agent``
   is constructed directly with the agent's system prompt.  When
   ``output_schema_path`` is set the JSON Schema is converted to a
   pydantic ``BaseModel`` via ``_json_schema_to_pydantic_model()`` and
   passed as ``result_type=`` so the LLM provider enforces the structure
   at the API level.  Otherwise the agent runs in freeform-text mode.

Usage extraction handles both pydantic-ai shapes:
- ``result.usage()`` callable → ``Usage.input_tokens`` / ``output_tokens``
  (or ``request_tokens`` / ``response_tokens`` for older API shapes).
- ``result.usage`` attribute → same attribute access.
- Falls back to 0/0 when usage is unavailable.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

from pydantic import BaseModel, ValidationError, create_model
from pydantic_ai import NativeOutput, PromptedOutput, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)
from agentbox.core.agent.config import PythonAgentConfig
from agentbox.core.run.backends._schema_to_model import (
    UnsupportedSchema,
    json_schema_to_pydantic_model,
)
from agentbox.core.run.backends.base import BackendAdapter, RenderedConfig


@dataclass(frozen=True)
class _RefSection:
    heading: str
    content: str


@dataclass(frozen=True)
class TokenDeps:
    """Runtime deps injected into pydantic-ai's ``RunContext``.

    Reference documents (markdown, skills, attached resources) ride
    through deps rather than being concatenated into the system prompt
    string. A dynamic ``@system_prompt`` reads ``ctx.deps.references``
    and renders the headings inline — this keeps the *base* system
    prompt small and lets the same backend handle agents with very
    different reference payloads without rebuilding the prompt string.
    """

    references: tuple[_RefSection, ...] = ()


_NAME = "token"


# ---------------------------------------------------------------------------
# Schema conversion helper (from pydantic_ai_structured)
# ---------------------------------------------------------------------------


def _json_schema_to_pydantic_model(
    schema: dict[str, Any],
    *,
    model_name: str = "OutputModel",
) -> Any:
    """Convert a JSON Schema dict to a pydantic ``BaseModel``.

    Handles the common shapes produced by ``model_json_schema()``:
    top-level ``$defs``, ``$ref`` resolution, ``required`` lists, and
    basic types (string, integer, number, boolean, array, object).

    Falls back to a generic ``dict`` model when the schema is too complex
    to translate automatically.
    """
    defs: dict[str, Any] = schema.get("$defs", {})

    def _resolve_ref(ref: str) -> dict[str, Any]:
        # "#/$defs/Foo" → "Foo"
        parts = ref.split("/")
        name = parts[-1]
        return defs.get(name, {})

    def _json_type_to_python(field_schema: dict[str, Any]) -> Any:
        typ = field_schema.get("type")
        if "$ref" in field_schema:
            resolved = _resolve_ref(field_schema["$ref"])
            sub = _build_model_from_schema(
                resolved, name=field_schema["$ref"].split("/")[-1]
            )
            return sub
        if typ == "string":
            return str
        if typ == "integer":
            return int
        if typ == "number":
            return float
        if typ == "boolean":
            return bool
        if typ == "array":
            items = field_schema.get("items", {})
            if "$ref" in items:
                resolved = _resolve_ref(items["$ref"])
                item_model = _build_model_from_schema(
                    resolved, name=items["$ref"].split("/")[-1]
                )
                return list[item_model]
            item_type = _json_type_to_python(items)
            return list[item_type] if item_type else list
        if typ == "object":
            return dict[str, Any]
        if typ == "null":
            return type(None)
        return Any

    def _build_model_from_schema(
        schema_obj: dict[str, Any],
        *,
        name: str = "NestedModel",
    ) -> Any:
        union_branches = schema_obj.get("oneOf") or schema_obj.get("anyOf")
        if union_branches:
            branch_types: list[Any] = []
            for i, branch in enumerate(union_branches):
                if "$ref" in branch:
                    resolved = _resolve_ref(branch["$ref"])
                    branch_name = branch["$ref"].split("/")[-1]
                    branch_types.append(
                        _build_model_from_schema(resolved, name=branch_name)
                    )
                else:
                    branch_name = branch.get("title") or f"{name}Branch{i}"
                    branch_types.append(
                        _build_model_from_schema(branch, name=branch_name)
                    )
            if len(branch_types) == 1:
                return branch_types[0]
            return Union[tuple(branch_types)]  # type: ignore[return-value]  # noqa: UP007

        properties = schema_obj.get("properties", {})
        required = set(schema_obj.get("required", []))
        fields: dict[str, tuple[type, Any]] = {}
        for prop_name, prop_schema in properties.items():
            py_type = _json_type_to_python(prop_schema)
            default = ... if prop_name in required else None
            if "default" in prop_schema and prop_name not in required:
                default = prop_schema["default"]
            fields[prop_name] = (py_type, default)
        if not fields:
            return create_model(name)
        return create_model(name, **fields)

    return _build_model_from_schema(schema, name=model_name)


def _format_provider_error(exc: Exception, *, model: str, provider: str | None) -> str:
    raw = str(exc)
    if isinstance(exc, ValidationError) and "finish_reason" in raw and "error" in raw:
        provider_name = provider or "unknown"
        return (
            f"OpenRouter/{provider_name} returned finish_reason='error' "
            f"for model={model} (upstream provider failure). Raw: {raw}"
        )

    try:
        from pydantic_ai.exceptions import UnexpectedModelBehavior
    except Exception:
        UnexpectedModelBehavior = None  # type: ignore[assignment]

    if UnexpectedModelBehavior is not None and isinstance(exc, UnexpectedModelBehavior):
        body = getattr(exc, "body", None)
        if body:
            return f"agent execution error: {exc}; body: {body}"

    return f"agent execution error: {exc}"


def _part_kind(part: Any) -> str:
    explicit = getattr(part, "part_kind", None) or getattr(part, "kind", None)
    if explicit:
        return str(explicit)
    return part.__class__.__name__.lower()


def _stringify_excerpt(value: Any, *, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, default=str)
        except Exception:
            text = str(value)
    return text[:limit]


def _iter_message_history_events(run_id: str, messages: Any) -> list[RunEvent]:
    events: list[RunEvent] = []
    for msg in messages or []:
        msg_kind = getattr(msg, "kind", "") or msg.__class__.__name__.lower()
        is_response = "response" in msg_kind or "model" in msg_kind
        for part in getattr(msg, "parts", []) or []:
            kind = _part_kind(part)
            if is_response and ("text" in kind and "tool" not in kind):
                text = getattr(part, "content", None) or getattr(part, "text", None)
                if text:
                    events.append(
                        TextEvent(run_id=run_id, role="assistant", text=str(text))
                    )
                continue
            if "thinking" in kind or "reasoning" in kind:
                text = (
                    getattr(part, "text", None)
                    or getattr(part, "content", None)
                    or getattr(part, "reasoning", None)
                )
                if text:
                    events.append(ThinkingEvent(run_id=run_id, text=str(text)))
                continue

            if "tool-call" in kind or "tool_call" in kind or "toolcall" in kind:
                tool = getattr(part, "tool_name", None) or getattr(part, "name", "")
                args = getattr(part, "args", None) or getattr(part, "arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                if not isinstance(args, dict):
                    args = {"value": args}
                call_id = (
                    getattr(part, "tool_call_id", None)
                    or getattr(part, "call_id", None)
                    or getattr(part, "id", None)
                )
                events.append(
                    ToolCallEvent(
                        run_id=run_id,
                        tool=str(tool),
                        arguments=args,
                        call_id=str(call_id) if call_id is not None else None,
                    )
                )
                continue

            if (
                "tool-return" in kind
                or "tool_return" in kind
                or "tool-result" in kind
                or "tool_result" in kind
                or "toolreturn" in kind
            ):
                tool = getattr(part, "tool_name", None) or getattr(part, "name", "")
                content = getattr(part, "content", None)
                call_id = (
                    getattr(part, "tool_call_id", None)
                    or getattr(part, "call_id", None)
                    or getattr(part, "id", None)
                )
                ok = not bool(getattr(part, "is_error", False))
                if hasattr(content, "success"):
                    ok = bool(content.success)
                events.append(
                    ToolResultEvent(
                        run_id=run_id,
                        tool=str(tool),
                        call_id=str(call_id) if call_id is not None else None,
                        ok=ok,
                        result_excerpt=_stringify_excerpt(content),
                    )
                )
    return events


def _emit_message_history(run_id: str, messages: Any) -> list[RunEvent]:
    try:
        return _iter_message_history_events(run_id, messages)
    except Exception as exc:
        return [
            LogEvent(
                run_id=run_id,
                level="warn",
                message=f"could not emit pydantic-ai message history: {exc}",
            )
        ]


# ---------------------------------------------------------------------------
# Backend adapter
# ---------------------------------------------------------------------------


class TokenBackend(BackendAdapter):
    """Unified in-process LLM backend using pydantic-ai."""

    name = _NAME
    conversation_format: str | None = "pydantic-ai-history"

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        # PydanticAI has no native session log; the source reconstructs
        # turns from the agentbox transcript itself.
        return transcript_path

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: list[dict] | None = None,
        creds: dict | None = None,
        runner_config: Any | None = None,
    ) -> RenderedConfig:
        python_cfg = PythonAgentConfig.from_agent(agent)
        model = getattr(runner_config, "model", None) or self.default_model

        # Load output schema for result_type construction (direct-agent mode).
        # Prefer the in-memory schema attached by the composition pipeline
        # (DB-only agents have no on-disk bundle to read from); fall back to
        # ``output_schema_path`` for legacy file-based agents.
        output_schema: dict[str, Any] | None = None
        composed_schema = getattr(agent, "_composed_schema", None)
        if isinstance(composed_schema, dict):
            output_schema = composed_schema
        elif python_cfg.output_schema_path:
            schema_path = workdir / python_cfg.output_schema_path
            if not schema_path.exists():
                # Try project_root from agent def if available.
                project_root = getattr(agent, "_project_root", None)
                if project_root is not None:
                    schema_path = Path(project_root) / python_cfg.output_schema_path
            if schema_path.exists():
                import contextlib

                with contextlib.suppress(json.JSONDecodeError, OSError):
                    output_schema = json.loads(
                        schema_path.read_text(encoding="utf-8")
                    )

        # Prefer the clean, schema-free base prompt when composition ran.
        # Pydantic-ai handles schema injection itself; the bundled
        # references go through deps. Falling back to ``_resolve_prompt``
        # (which returns the fully-composed string) keeps legacy callers
        # working — those won't have a schema mismatch since no result_type
        # is being attached either.
        system_base = getattr(agent, "_composed_system_base", None)
        prompt = system_base if isinstance(system_base, str) and system_base else self._resolve_prompt(agent, workdir)

        references = getattr(agent, "_composed_references", ()) or ()
        input_schema = getattr(agent, "_composed_input_schema", None)

        agent_meta: dict[str, Any] = {
            "agent_module": python_cfg.agent_module,
            "prompt": prompt,
            "agent_id": agent.id,
            "model": model,
            "output_schema": output_schema,
            "input_schema": input_schema if isinstance(input_schema, dict) else None,
            "references": [
                {"heading": r.heading, "content": r.content} for r in references
            ],
            "timeout_seconds": getattr(getattr(agent, "runner", None), "timeout_seconds", None),
        }

        # Store provider routing info from runner_config if present.
        if runner_config is not None:
            if getattr(runner_config, "provider", None):
                agent_meta["provider"] = runner_config.provider
            if getattr(runner_config, "model", None):
                agent_meta["model"] = runner_config.model
            if getattr(runner_config, "api_key_env", None):
                agent_meta["api_key_env"] = runner_config.api_key_env
            if getattr(runner_config, "base_url", None):
                agent_meta["base_url"] = runner_config.base_url
            if getattr(runner_config, "profile_id", None):
                agent_meta["profile_id"] = runner_config.profile_id
            if getattr(runner_config, "output_mode", None):
                agent_meta["output_mode"] = runner_config.output_mode

        return RenderedConfig(
            cwd=Path("."),
            files=self._collect_system_files(agent, workdir),
            agent_meta=agent_meta,
            model=model,
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        agent_module = rendered.agent_meta.get("agent_module")
        prompt = rendered.agent_meta.get("prompt", "")
        model_str = rendered.agent_meta.get("model") or "openai:gpt-4o"
        output_schema = rendered.agent_meta.get("output_schema")

        yield LogEvent(
            run_id=run_id,
            message=f"token backend: running with model={model_str}",
        )

        # Resolve provider routing config.
        provider = rendered.agent_meta.get("provider")
        api_key_env = rendered.agent_meta.get("api_key_env")
        base_url = rendered.agent_meta.get("base_url")
        output_mode = (rendered.agent_meta.get("output_mode") or "auto").lower()
        model = rendered.model or model_str

        api_key: str | None = None
        if provider and api_key_env:
            api_key = os.environ.get(api_key_env)
            if api_key is None:
                yield DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=f"API key env {api_key_env!r} not set",
                )
                return

        # Parse input. Full-agent mode (agent_module set) requires a structured
        # JSON payload to validate against the agent's request model. Direct
        # mode treats input as a plain user message; we still try JSON first so
        # callers passing structured payloads get the pretty-printed dict body.
        input_data: Any
        if not input:
            input_data = {} if agent_module else ""
        else:
            try:
                input_data = json.loads(input)
            except json.JSONDecodeError as exc:
                if agent_module:
                    yield DoneEvent(
                        run_id=run_id, ok=False, error=f"invalid input JSON: {exc}"
                    )
                    return
                input_data = input

        if agent_module:
            # ------------------------------------------------------------------
            # Full-agent mode: import user's BaseAgent subclass and run it.
            # ------------------------------------------------------------------
            try:
                agent_cls = self._import_agent(agent_module)
            except (ImportError, ValueError) as exc:
                yield DoneEvent(run_id=run_id, ok=False, error=str(exc))
                return

            # Build and validate the request model.
            request_model = self._resolve_request_model(agent_cls)
            try:
                request = request_model.model_validate(input_data)
            except Exception as exc:
                yield DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=f"input validation error: {exc}",
                )
                return

            # Resolve MCP URL from env or config.
            mcp_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/mcp/")

            # Instantiate the agent.
            try:
                agent_kwargs: dict[str, Any] = {"mcp_url": mcp_url}
                if provider and api_key and base_url:
                    agent_kwargs["api_key"] = api_key
                    agent_kwargs["base_url"] = base_url
                if model and provider:
                    agent_kwargs["model"] = model
                agent_instance = agent_cls(**agent_kwargs)
            except TypeError:
                # Fall back to mcp_url-only init if extended kwargs not supported.
                try:
                    agent_instance = agent_cls(mcp_url=mcp_url)
                except Exception as exc:
                    yield DoneEvent(
                        run_id=run_id,
                        ok=False,
                        error=f"agent instantiation error: {exc}",
                    )
                    return
            except Exception as exc:
                yield DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=f"agent instantiation error: {exc}",
                )
                return

            # Run the agent synchronously.
            start = time.monotonic()
            try:
                try:
                    system_prompt, user_message = agent_instance.render_prompts(request)
                except Exception:
                    system_prompt = prompt
                    user_message = json.dumps(input_data, indent=2, default=str)
                yield TextEvent(run_id=run_id, role="system", text=system_prompt)
                yield TextEvent(run_id=run_id, role="user", text=user_message)
                result = agent_instance.run_sync(request)
            except Exception as exc:
                err_text = _format_provider_error(
                    exc, model=model_str, provider=provider
                )
                yield LogEvent(run_id=run_id, level="error", message=err_text)
                yield DoneEvent(
                    run_id=run_id, ok=False, error=err_text, status="error"
                )
                return
            _elapsed = time.monotonic() - start

            for ev in _emit_message_history(
                run_id, getattr(agent_instance, "_message_history", [])
            ):
                yield ev

            # Serialize output (result is the return value directly).
            try:
                if hasattr(result, "model_dump_json"):
                    output_text = result.model_dump_json()
                elif hasattr(result, "model_dump"):
                    output_text = json.dumps(result.model_dump())
                else:
                    output_text = json.dumps(result, default=str)
            except Exception as exc:
                yield DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=f"output serialization error: {exc}",
                )
                return

            yield TextEvent(run_id=run_id, text=output_text)
            yield UsageEvent(
                run_id=run_id,
                input_tokens=0,
                output_tokens=0,
                cost_usd=None,
                model=getattr(agent_instance, "model", None),
            )
            yield DoneEvent(run_id=run_id, ok=True)
            return

        # ----------------------------------------------------------------------
        # Direct-agent mode: use pydantic_ai.Agent directly.
        # ----------------------------------------------------------------------
        try:
            from pydantic_ai import Agent
        except ImportError:
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=(
                    "pydantic-ai is not installed. "
                    "Install it to use the token backend."
                ),
            )
            return

        # Build result_type from output schema when present. The strict
        # converter preserves enums, length/pattern, ranges and
        # ``additionalProperties=false`` so pydantic-ai's own validation
        # matches the JSON Schema the agent was authored against. If the
        # schema uses a construct the strict converter can't translate,
        # fall back to the loose converter (basic types only) and log a
        # warning rather than failing the run — losing some constraints
        # is better than aborting.
        input_schema = rendered.agent_meta.get("input_schema")
        result_type: Any = None
        if output_schema:
            try:
                result_type = json_schema_to_pydantic_model(
                    output_schema,
                    model_name="AgentOutput",
                )
            except UnsupportedSchema as exc:
                yield LogEvent(
                    run_id=run_id,
                    level="warn",
                    message=(
                        f"strict schema conversion failed ({exc}); "
                        "falling back to loose conversion — pydantic-ai "
                        "validation will be looser than the JSON Schema."
                    ),
                )
                try:
                    result_type = _json_schema_to_pydantic_model(
                        output_schema,
                        model_name="AgentOutput",
                    )
                except Exception as fallback_exc:
                    yield DoneEvent(
                        run_id=run_id,
                        ok=False,
                        error=f"schema-to-model conversion error: {fallback_exc}",
                    )
                    return
            except Exception as exc:
                yield DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=f"schema-to-model conversion error: {exc}",
                )
                return

        # Validate input against input_schema if declared. Mirrors the
        # full-agent mode contract — the agent's instructions reference
        # the input shape; sending a payload that doesn't match wastes
        # tokens and confuses the model.
        if isinstance(input_schema, dict) and isinstance(input_data, dict):
            try:
                input_model = json_schema_to_pydantic_model(
                    input_schema,
                    model_name="AgentInput",
                )
                input_model.model_validate(input_data)
            except UnsupportedSchema as exc:
                yield LogEvent(
                    run_id=run_id,
                    level="warn",
                    message=f"could not validate input against input_schema: {exc}",
                )
            except ValidationError as exc:
                yield DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=f"input validation error: {exc}",
                )
                return

        # Build user message.
        user_message = (
            json.dumps(input_data, indent=2) if isinstance(input_data, dict) else str(input_data)
        )

        # Instantiate and run pydantic-ai Agent.
        start = time.monotonic()

        # Wrap result_type per the profile's output_mode. ``auto`` and
        # ``tool`` map to the pydantic-ai default (forced tool_choice on
        # an output tool). ``prompted`` injects the schema in the system
        # prompt and parses JSON from the response — required for
        # reasoning models (e.g. DeepSeek V4 Pro) that reject forced
        # tool_choice. ``native`` uses the provider's structured-output
        # mode where supported.
        wrapped_output_type: Any = None
        if result_type is not None:
            if output_mode == "prompted":
                wrapped_output_type = PromptedOutput(result_type)
            elif output_mode == "native":
                wrapped_output_type = NativeOutput(result_type)
            else:
                wrapped_output_type = result_type

        # Build reference deps. References ride through pydantic-ai's
        # ``RunContext`` instead of being concatenated onto the system
        # prompt — a dynamic ``@system_prompt`` handler renders them
        # below. This keeps the static base prompt small and makes the
        # references inspectable as deps rather than buried in a string.
        ref_payload = rendered.agent_meta.get("references") or []
        deps = TokenDeps(
            references=tuple(
                _RefSection(heading=r["heading"], content=r["content"])
                for r in ref_payload
                if isinstance(r, dict) and r.get("heading") and r.get("content")
            )
        )

        common_kwargs: dict[str, Any] = {
            "system_prompt": prompt,
            "deps_type": TokenDeps,
        }
        if wrapped_output_type is not None:
            common_kwargs["output_type"] = wrapped_output_type

        if base_url:
            # Strip provider prefix (e.g. "openrouter:google/gemini-2.5-flash-lite"
            # → "google/gemini-2.5-flash-lite") for OpenAI-compatible endpoints.
            short_model = model_str.split(":", 1)[1] if ":" in model_str else model_str
            # Local providers (e.g. Ollama) accept any string as api_key; use a
            # dummy when none is configured rather than failing OpenAIProvider's
            # required-key validation.
            provider_obj = OpenAIProvider(
                api_key=api_key or "no-key",
                base_url=base_url,
            )
            pai_model = OpenAIModel(short_model, provider=provider_obj)
            pai_agent = Agent(pai_model, **common_kwargs)
        else:
            pai_agent = Agent(model_str, **common_kwargs)

        @pai_agent.system_prompt
        def _render_refs(ctx: RunContext[TokenDeps]) -> str:
            sections = ctx.deps.references if ctx.deps else ()
            if not sections:
                return ""
            return "\n\n".join(
                f"## {s.heading}\n\n{s.content}" for s in sections
            )

        # We're inside an async generator — pydantic-ai's run_sync() would
        # try to start its own event loop and fail. Use the async API.
        yield TextEvent(run_id=run_id, role="system", text=prompt)
        yield TextEvent(run_id=run_id, role="user", text=user_message)
        yield LogEvent(
            run_id=run_id,
            message=f"sending to model {model_str}...",
        )
        # Use run_stream_events() so every token / thinking chunk
        # is emitted to the transcript in real time, regardless of
        # whether the final structured-output parse succeeds.
        thinking_accum: dict[int, str] = {}
        text_accum: dict[int, str] = {}
        final_result: Any = None
        try:
            async with pai_agent.run_stream_events(user_message, deps=deps) as stream:
                async for event in stream:
                    et = type(event).__name__
                    if et == "PartStartEvent":
                        idx: int = getattr(event, "index", 0)
                        pn = type(event.part).__name__
                        if "Thinking" in pn:
                            thinking_accum[idx] = getattr(event.part, "content", "")
                        elif "Text" in pn:
                            text_accum[idx] = getattr(event.part, "content", "")
                    elif et == "PartDeltaEvent":
                        idx = getattr(event, "index", 0)
                        dn = type(event.delta).__name__
                        delta_text: str = getattr(event.delta, "content_delta", "")
                        if "Thinking" in dn and delta_text:
                            thinking_accum[idx] = thinking_accum.get(idx, "") + delta_text
                            yield ThinkingEvent(run_id=run_id, text=delta_text)
                        elif "Text" in dn and delta_text:
                            text_accum[idx] = text_accum.get(idx, "") + delta_text
                            yield TextEvent(
                                run_id=run_id,
                                text=delta_text,
                                delta=True,
                            )
                    elif et == "PartEndEvent":
                        idx = getattr(event, "index", 0)
                        pn = type(event.part).__name__
                        if "Thinking" in pn:
                            thinking_accum[idx] = getattr(event.part, "content", "")
                        elif "Text" in pn:
                            text_accum[idx] = getattr(event.part, "content", "")
                    elif et == "AgentRunResultEvent":
                        final_result = getattr(event, "result", None)
        except Exception as exc:
            err_text = _format_provider_error(exc, model=model_str, provider=provider)
            # Emit whatever partial output was captured before the error.
            for acc in (thinking_accum, text_accum):
                for text in acc.values():
                    if text:
                        yield TextEvent(run_id=run_id, text=text)
            body = getattr(exc, "body", None)
            if body:
                yield LogEvent(
                    run_id=run_id,
                    level="info",
                    message=f"model raw response: {body}",
                )
            yield LogEvent(run_id=run_id, level="error", message=err_text)
            yield DoneEvent(
                run_id=run_id, ok=False, error=err_text, status="error"
            )
            return
        _elapsed = time.monotonic() - start

        # Reconstruct result for downstream processing.
        result = final_result

        all_messages = getattr(result, "all_messages", None)
        if callable(all_messages):
            # Deltas already streamed the assistant text in this code path,
            # so re-emitting the message history's TextEvents would cause a
            # second non-delta assistant TextEvent to land in
            # ``session.output_text`` alongside the serialized result below,
            # producing concatenated duplicate JSON for Ollama (and any
            # other text-mode provider). Keep tool/thinking events for
            # provenance; drop text.
            for ev in _emit_message_history(run_id, all_messages()):
                if isinstance(ev, TextEvent):
                    continue
                yield ev

        # Serialize output. pydantic-ai 1.x exposes ``.output``; pre-1.x used ``.data``.
        try:
            output_data = getattr(result, "output", None)
            if output_data is None:
                output_data = result.data
            if hasattr(output_data, "model_dump_json"):
                output_text = output_data.model_dump_json()
            elif hasattr(output_data, "model_dump"):
                output_text = json.dumps(output_data.model_dump())
            else:
                output_text = json.dumps(output_data, default=str)
        except Exception as exc:
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=f"output serialization error: {exc}",
            )
            return

        yield TextEvent(run_id=run_id, text=output_text)

        # Extract usage — handle both callable and attribute shapes, and both
        # request_tokens/response_tokens (older pydantic-ai) and
        # input_tokens/output_tokens (newer).
        raw_usage = getattr(result, "usage", None)
        if callable(raw_usage):
            try:
                raw_usage = raw_usage()
            except Exception:
                raw_usage = None
        if raw_usage is not None:
            input_tokens = (
                getattr(raw_usage, "input_tokens", None)
                or getattr(raw_usage, "request_tokens", None)
                or 0
            )
            output_tokens = (
                getattr(raw_usage, "output_tokens", None)
                or getattr(raw_usage, "response_tokens", None)
                or 0
            )
            model_name = getattr(raw_usage, "model", None)
        else:
            input_tokens = 0
            output_tokens = 0
            model_name = None

        yield UsageEvent(
            run_id=run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=None,
            model=model_name,
        )

        yield DoneEvent(run_id=run_id, ok=True)

    # --------------------------------------------------------------------------
    # Import / class helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def _import_agent(module_path: str) -> type:
        """Import a pydantic-ai Agent class from a ``module.path:ClassName`` string.

        Adds ``project_root`` (from env ``AGENTBOX_PROJECT_ROOT``) to
        ``sys.path`` so project-local modules (``apps.*``, ``agents.*``)
        are importable without Django.
        """
        project_root = os.environ.get("AGENTBOX_PROJECT_ROOT", "/project")
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
            libs_dir = os.path.join(project_root, "libs")
            if os.path.isdir(libs_dir) and libs_dir not in sys.path:
                sys.path.insert(0, libs_dir)
            src_dir = os.path.join(project_root, "src")
            if os.path.isdir(src_dir) and src_dir not in sys.path:
                sys.path.insert(0, src_dir)

        module_name, _, class_name = module_path.partition(":")
        if not class_name:
            raise ValueError(
                f"agent_module must be in 'module.path:ClassName' format, "
                f"got {module_path!r}"
            )
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(
                f"cannot import agent module {module_name!r}: {exc}"
            ) from exc
        try:
            cls = getattr(module, class_name)
        except AttributeError as exc:
            raise ImportError(
                f"agent class {class_name!r} not found in {module_name!r}"
            ) from exc
        return cls

    @staticmethod
    def _resolve_request_model(agent_cls: type) -> type:
        """Return the request model class for a pydantic-ai BaseAgent subclass."""
        if hasattr(agent_cls, "INPUT_TYPE") and agent_cls.INPUT_TYPE is not None:
            return agent_cls.INPUT_TYPE

        # Try to extract from generic base (BaseAgent[RequestModel, ResponseModel]).
        for base in getattr(agent_cls, "__orig_bases__", []):
            args = getattr(base, "__args__", [])
            if args:
                return args[0]

        # Fallback: accept any dict.
        from pydantic import Field

        class _GenericInput(BaseModel):
            data: dict[str, Any] = Field(default_factory=dict)

        return _GenericInput

    @staticmethod
    def _auto_generate_agent(agent_id: str, system_prompt: str) -> type:
        """Dynamically create a pydantic-agents BaseAgent class from a markdown prompt.

        The generated agent:
        - Uses ``system_prompt`` as its system prompt.
        - Accepts ``dict[str, Any]`` as input.
        - Returns ``dict[str, Any]`` as output.
        - No custom tools.
        """
        from pydantic import Field

        try:
            from pydantic_agents import BaseAgent
        except ImportError as exc:
            raise ImportError(
                "pydantic_agents is required for auto-generated agents. "
                "Install it or set agent_module on the RunnerSpec instead."
            ) from exc

        class _AutoRequest(BaseModel):
            data: dict[str, Any] = Field(default_factory=dict)

        class _AutoResponse(BaseModel):
            result: dict[str, Any] = Field(default_factory=dict)
            raw_text: str = ""

        class _AutoGeneratedAgent(BaseAgent[_AutoRequest, _AutoResponse]):  # type: ignore[type-arg]
            OUTPUT_TYPE = _AutoResponse
            _SYSTEM_PROMPT = system_prompt

            def build_system_prompt(self) -> str:
                return self._SYSTEM_PROMPT

        _AutoGeneratedAgent.__name__ = f"AutoAgent_{agent_id.replace('.', '_')}"
        return _AutoGeneratedAgent
