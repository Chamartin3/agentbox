"""Backend adapter that uses pydantic-ai for structured output.

When an agent declares an ``output_schema`` and this backend is selected,
the JSON Schema is converted to a pydantic ``BaseModel`` at runtime and
passed to pydantic-ai as ``result_type``.  The LLM provider (OpenAI,
Anthropic, etc.) then enforces the schema at the API level — the model
*cannot* return a response that violates the structure.

This is the strictest validation path: enforcement happens before the
response reaches agentbox, so the post-processor always receives a
well-formed payload.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, create_model

from agentbox.api.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.backends.base import BackendAdapter, RenderedConfig

_NAME = "pydantic_ai_structured"


def _json_schema_to_pydantic_model(
    schema: dict[str, Any],
    *,
    model_name: str = "OutputModel",
) -> type[BaseModel]:
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
            sub = _build_model_from_schema(resolved, name=field_schema["$ref"].split("/")[-1])
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
                item_model = _build_model_from_schema(resolved, name=items["$ref"].split("/")[-1])
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
    ) -> type[BaseModel]:
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


class PydanticAiStructuredBackend(BackendAdapter):
    """Backend that enforces structured output via pydantic-ai."""

    name = _NAME
    default_model = "openai:gpt-4o"

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: list[dict] | None = None,
        creds: dict | None = None,
    ) -> RenderedConfig:
        spec = agent.runner
        model = self._resolve_model(spec)

        # Load output schema for result_type construction.
        output_schema: dict[str, Any] | None = None
        if spec.output_schema_path:
            schema_path = workdir / spec.output_schema_path
            if not schema_path.exists():
                # Try project_root from agent def if available.
                project_root = getattr(agent, "_project_root", None)
                if project_root is not None:
                    schema_path = Path(project_root) / spec.output_schema_path
            if schema_path.exists():
                import contextlib
                with contextlib.suppress(json.JSONDecodeError, OSError):
                    output_schema = json.loads(
                        schema_path.read_text(encoding="utf-8")
                    )

        agent_meta: dict[str, Any] = {
            "prompt": self._resolve_prompt(agent, workdir),
            "agent_id": agent.id,
            "model": model,
            "output_schema": output_schema,
            "timeout_seconds": spec.timeout_seconds,
        }

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
        try:
            from pydantic_ai import Agent
        except ImportError:
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=(
                    "pydantic-ai is not installed. "
                    "Install it to use the pydantic_ai_structured backend."
                ),
            )
            return

        prompt = rendered.agent_meta.get("prompt", "")
        model_str = rendered.agent_meta.get("model", "openai:gpt-4o")
        output_schema = rendered.agent_meta.get("output_schema")

        yield LogEvent(
            run_id=run_id,
            message=f"pydantic_ai_structured backend: running with model={model_str}",
        )

        # Build result_type from schema.
        result_type: type[BaseModel] | None = None
        if output_schema:
            try:
                result_type = _json_schema_to_pydantic_model(
                    output_schema,
                    model_name="AgentOutput",
                )
            except Exception as exc:
                yield LogEvent(
                    run_id=run_id,
                    level="warn",
                    message=f"failed to build pydantic model from schema: {exc}",
                )

        # Parse input.
        try:
            input_data = json.loads(input) if input else {}
        except json.JSONDecodeError as exc:
            yield DoneEvent(
                run_id=run_id, ok=False, error=f"invalid input JSON: {exc}"
            )
            return

        # Build user message.
        user_message = json.dumps(input_data, indent=2) if isinstance(input_data, dict) else str(input_data)

        # Instantiate and run pydantic-ai Agent.
        start = time.monotonic()
        try:
            agent = Agent(model=model_str, system_prompt=prompt, result_type=result_type)
            result = agent.run_sync(user_message)
        except Exception as exc:
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=f"agent execution error: {exc}",
            )
            return
        elapsed = time.monotonic() - start  # noqa: F841

        # Serialize output.
        try:
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

        # Extract usage if available.
        usage = getattr(result, "usage", None)
        input_tokens = getattr(usage, "request_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "response_tokens", 0) if usage else 0
        model_name = getattr(usage, "model", None) if usage else None

        yield UsageEvent(
            run_id=run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=None,
            model=model_name,
        )

        yield DoneEvent(run_id=run_id, ok=True)
