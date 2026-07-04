"""Direct-agent execution path for ``TokenBackend``.

Used when no ``agent_module`` is configured — we construct a
``pydantic_ai.Agent`` here, optionally with a JSON-Schema-derived
``result_type`` so the provider enforces structured output. Streaming
events from ``pydantic_ai.Agent.run_stream_events`` are translated
into agentbox :class:`RunEvent` deltas inline so the transcript
captures every token.

Split out of ``_backend.py`` to keep the main module focused on the
``BackendAdapter`` contract; the streaming-loop body is the bulk of
the original 993-LOC module.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError
from pydantic_ai import Agent, NativeOutput, PromptedOutput, RunContext
# OpenAIChatModel is pydantic-ai's canonical class; the old OpenAIModel name is
# now a deprecated subclass. Import the canonical name (aliased for local use).
from pydantic_ai.models.openai import OpenAIChatModel as OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agentbox.core.data.payload_types import GrantConfig, JsonSchemaDict, ModelParams, RefSection
from agentbox.core.data.constants import LogLevel, MessageRole, RunStatus
from agentbox.core.data.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    UsageEvent,
)
from agentbox.core.engines.contracts.schema_to_model import (
    UnsupportedSchema,
    json_schema_to_pydantic_model,
)
from agentbox.core.engines.backends.token.schema import _json_schema_to_pydantic_model
from agentbox.core.engines.backends.token.tools import (
    build_host_env_toolsets,
    build_host_env_tools,
)
from agentbox.core.engines.backends.token.stream import (
    _RefSection,
    TokenDeps,
    _emit_message_history,
    _format_provider_error,
)
from agentbox.core.engines.backends.token.usage import extract_usage


class _OllamaCompatModel(OpenAIModel):
    """OpenAI-compat model that never replays a null-content assistant turn.

    A reasoning model (e.g. Qwen3) often emits a turn that is *only* a thinking
    part — no text, no tool call. pydantic-ai serializes that as
    ``{"role":"assistant","reasoning":...,"content":null}``. The real OpenAI API
    accepts null assistant content, but Ollama's OpenAI-compat endpoint rejects
    it with ``400 invalid message content type: <nil>`` unless ``tool_calls`` is
    also present — so the very next round-trip (which replays that turn in the
    history) kills the run before the model ever fires its tool call. Coercing
    null → "" is universally accepted and changes nothing semantically.
    """

    def _map_model_response(self, message: Any) -> Any:  # noqa: ANN401
        mapped = super()._map_model_response(message)
        if (
            mapped is not None
            and mapped.get("role") == "assistant"
            and mapped.get("content") is None
        ):
            mapped["content"] = ""
        return mapped


async def run_direct_agent_mode(
    *,
    run_id: str,
    prompt: str,
    model_str: str,
    output_schema: JsonSchemaDict | None,
    input_schema: JsonSchemaDict | None,
    output_mode: str,
    provider: str | None,
    api_key: str | None,
    base_url: str | None,
    output_retries: Any,
    references: list[RefSection],
    input_data: Any,
    host_env_grants: dict[str, GrantConfig] | None = None,
    agent_tool_grants: set[str] | None = None,
    workspace_id: str | None = None,
    workdir: str | None = None,
    db_path: str | None = None,
    model_params: ModelParams | None = None,
) -> AsyncIterator[RunEvent]:
    """Drive a directly-constructed ``pydantic_ai.Agent`` to completion."""
    # Build result_type from output schema when present. The strict
    # converter preserves enums, length/pattern, ranges and
    # ``additionalProperties=false`` so pydantic-ai's own validation
    # matches the JSON Schema the agent was authored against. If the
    # schema uses a construct the strict converter can't translate,
    # fall back to the loose converter (basic types only) and log a
    # warning rather than failing the run — losing some constraints
    # is better than aborting.
    result_type: Any = None
    if output_schema:
        try:
            result_type = json_schema_to_pydantic_model(
                dict(output_schema),
                model_name="AgentOutput",
            )
        except UnsupportedSchema as exc:
            yield LogEvent(
                run_id=run_id,
                level=LogLevel.WARN,
                message=(
                    f"strict schema conversion failed ({exc}); "
                    "falling back to loose conversion — pydantic-ai "
                    "validation will be looser than the JSON Schema."
                ),
            )
            try:
                result_type = _json_schema_to_pydantic_model(
                    dict(output_schema),
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
                dict(input_schema),
                model_name="AgentInput",
            )
            input_model.model_validate(input_data)
        except UnsupportedSchema as exc:
            yield LogEvent(
                run_id=run_id,
                level=LogLevel.WARN,
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
        json.dumps(input_data, indent=2)
        if isinstance(input_data, dict)
        else str(input_data)
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
    deps = TokenDeps(
        references=tuple(
            _RefSection(heading=r["heading"], content=r["content"])
            for r in references
            if isinstance(r, dict) and r.get("heading") and r.get("content")
        )
    )

    common_kwargs: dict[str, Any] = {
        "system_prompt": prompt,
        "deps_type": TokenDeps,
    }
    if wrapped_output_type is not None:
        common_kwargs["output_type"] = wrapped_output_type
    if isinstance(output_retries, int) and output_retries > 0:
        common_kwargs["output_retries"] = output_retries

    # Runner-profile ``params`` map 1:1 onto pydantic-ai ModelSettings keys
    # (max_tokens, temperature, extra_body, ...). Passing them as model_settings
    # is what lets local reasoning models be tamed, e.g.
    # params = {"extra_body": {"reasoning_effort": "none"}} disables qwen3's
    # thinking on the Ollama /v1 endpoint (verified: kills the degenerate
    # thinking loops). Previously these params were silently dropped.
    if model_params:
        common_kwargs["model_settings"] = dict(model_params)

    # Wire the host-env tools so the model can actually call them. Without this
    # the direct path presents zero tools and every model can only hallucinate
    # file contents (the .mcp.json route only works for MCP-aware backends like
    # claude_code, not the raw pydantic-ai path).
    #
    # Parity first: connect to the SAME host-env stdio MCP server every other
    # backend uses (full grant-enforced capability surface, single source). If
    # that's unavailable, fall back to the in-process fs.read/fs.list tools.
    mcp_toolsets = build_host_env_toolsets(
        host_env_grants, workspace_id, workdir, db_path
    )
    if mcp_toolsets:
        common_kwargs["toolsets"] = mcp_toolsets
        yield LogEvent(
            run_id=run_id,
            message=f"token backend: wired host-env MCP toolset "
            f"({len(mcp_toolsets)} server(s))",
        )
    else:
        host_env_tools = build_host_env_tools(host_env_grants, agent_tool_grants)
        if host_env_tools:
            common_kwargs["tools"] = host_env_tools
            yield LogEvent(
                run_id=run_id,
                message=f"token backend: wired {len(host_env_tools)} in-process "
                "host-env tool(s): " + ", ".join(t.__name__ for t in host_env_tools),
            )

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
        pai_model = _OllamaCompatModel(short_model, provider=provider_obj)
        pai_agent = Agent(pai_model, **common_kwargs)
    else:
        pai_agent = Agent(model_str, **common_kwargs)

    @pai_agent.system_prompt
    def _render_refs(ctx: RunContext[TokenDeps]) -> str:
        sections = ctx.deps.references if ctx.deps else ()
        if not sections:
            return ""
        return "\n\n".join(f"## {s.heading}\n\n{s.content}" for s in sections)

    # We're inside an async generator — pydantic-ai's run_sync() would
    # try to start its own event loop and fail. Use the async API.
    yield TextEvent(run_id=run_id, role=MessageRole.SYSTEM, text=prompt)
    yield TextEvent(run_id=run_id, role=MessageRole.USER, text=user_message)
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
    # MCP toolsets must be entered before the run so the stdio server spawns and
    # its tools are discovered. Only needed when MCP toolsets are wired; the
    # in-process/no-tool paths skip it (and keep plain test doubles working).
    # Closed on both the success and error paths below.
    if mcp_toolsets:
        await pai_agent.__aenter__()
    try:
        async with pai_agent.run_stream_events(user_message, deps=deps) as stream:
            async for event in stream:
                et = type(event).__name__
                if et == "PartStartEvent":
                    idx: int = getattr(event, "index", 0)
                    part = getattr(event, "part", None)
                    pn = type(part).__name__
                    if "Thinking" in pn:
                        thinking_accum[idx] = getattr(part, "content", "")
                    elif "Text" in pn:
                        text_accum[idx] = getattr(part, "content", "")
                elif et == "PartDeltaEvent":
                    idx = getattr(event, "index", 0)
                    delta = getattr(event, "delta", None)
                    dn = type(delta).__name__
                    delta_text: str = getattr(delta, "content_delta", "")
                    if "Thinking" in dn and delta_text:
                        thinking_accum[idx] = (
                            thinking_accum.get(idx, "") + delta_text
                        )
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
                    part = getattr(event, "part", None)
                    pn = type(part).__name__
                    if "Thinking" in pn:
                        thinking_accum[idx] = getattr(part, "content", "")
                    elif "Text" in pn:
                        text_accum[idx] = getattr(part, "content", "")
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
                level=LogLevel.INFO,
                message=f"model raw response: {body}",
            )
        yield LogEvent(run_id=run_id, level=LogLevel.ERROR, message=err_text)
        yield DoneEvent(run_id=run_id, ok=False, error=err_text, status=RunStatus.ERROR)
        return
    finally:
        # Close on the success path (and any non-Exception exit). Suppressed so
        # toolset teardown never masks the run result.
        if mcp_toolsets:
            with contextlib.suppress(Exception):
                await pai_agent.__aexit__(None, None, None)
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

    input_tokens, output_tokens, model_name = extract_usage(result)
    yield UsageEvent(
        run_id=run_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=None,
        model=model_name,
    )

    yield DoneEvent(run_id=run_id, ok=True)
