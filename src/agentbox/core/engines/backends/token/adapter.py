"""``TokenBackend`` — unified in-process pydantic-ai backend adapter.

The public class lives here; the package ``__init__`` re-exports it so
the entry point ``token = agentbox.core.engines.backends.token:TokenBackend``
keeps working after the split from the legacy single-module layout.

The two execution modes are factored into sibling modules:

* :mod:`._run_full` — ``agent_module`` set; imports the user's
  ``BaseAgent`` subclass and runs ``run_sync``.
* :mod:`._run_direct` — ``agent_module`` unset; instantiates
  ``pydantic_ai.Agent`` directly, optionally with a
  ``result_type`` derived from the agent's output JSON Schema.

This module retains only the :class:`BackendAdapter` contract surface
(``render`` and the ``run`` dispatch) plus a couple of staticmethod
shims for backward compatibility.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from agentbox.core.db import DoneEvent, LogEvent, RunEvent
from agentbox.core.engines.contracts.base import BackendAdapter, HasAgentConfig, RenderedConfig
from agentbox.core.engines.contracts.views import PythonAgentConfigView
from agentbox.core.engines.backends.token.run_direct import run_direct_agent_mode
from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.translation import intersect_allowed_tools
from agentbox.core.engines.backends.token.run_full import (
    import_agent,
    resolve_request_model,
    run_full_agent_mode,
)

_NAME = "token"


def _python_agent_config_view_from_agent(agent: HasAgentConfig) -> PythonAgentConfigView:
    """Fallback: read python config from the agent's ``_config_json``.

    Needed only when the executor does NOT supply ``python_agent_config``
    explicitly (e.g. direct ``render()`` calls in tests).
    """
    raw = getattr(agent, "_config_json", None)
    if raw is None:
        return PythonAgentConfigView()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return PythonAgentConfigView()
    python_section = (raw or {}).get("python") if isinstance(raw, dict) else None
    if not isinstance(python_section, dict):
        return PythonAgentConfigView()
    return PythonAgentConfigView(
        agent_module=python_section.get("agent_module"),
        output_schema_path=python_section.get("output_schema_path"),
    )


class TokenBackend(BackendAdapter):
    """Unified in-process LLM backend using pydantic-ai."""

    name = _NAME
    conversation_format: ClassVar[str | None] = "pydantic-ai-history"

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
        mcp_tools: Any = None,
        creds: dict | None = None,
        runner_config: Any | None = None,
        composed: Any | None = None,
        *,
        python_agent_config: PythonAgentConfigView | None = None,
        runtime_config: Any = None,
        host_capabilities: dict | None = None,
        ws_allowed_tools: set[CanonicalTool] | None = None,
        **kwargs: Any,
    ) -> RenderedConfig:
        python_cfg = (
            python_agent_config
            if python_agent_config is not None
            else _python_agent_config_view_from_agent(agent)
        )
        model = getattr(runner_config, "model", None) or self.default_model

        # Effective tools = agent ∩ workspace (canonical).
        effective_tools: set = set()
        if runtime_config is not None:
            effective_tools = intersect_allowed_tools(
                set(runtime_config.allowed_tools),
                ws_allowed_tools,
            )

        # Load output schema …
        output_schema: dict[str, Any] | None = None
        composed_schema = composed.schema if composed is not None else None
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
                with contextlib.suppress(json.JSONDecodeError, OSError):
                    output_schema = json.loads(schema_path.read_text(encoding="utf-8"))

        # Prefer the clean, schema-free base prompt when composition ran.
        # Pydantic-ai handles schema injection itself; the bundled
        # references go through deps. Falling back to ``_resolve_prompt``
        # (which returns the fully-composed string) keeps legacy callers
        # working — those won't have a schema mismatch since no result_type
        # is being attached either.
        system_base = composed.system_base if composed is not None else None
        prompt = (
            system_base
            if isinstance(system_base, str) and system_base
            else self._resolve_prompt(agent, workdir, composed)
        )

        references = (composed.references if composed is not None else ()) or ()
        input_schema = composed.input_schema if composed is not None else None

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
            "timeout_seconds": getattr(
                getattr(agent, "runner", None), "timeout_seconds", None
            ),
            "effective_tools": sorted(effective_tools),
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

        # Surface the agent's validation-retry budget so pydantic-ai's
        # own structured-output retry loop matches the executor's retry
        # budget. Default 1 (pydantic-ai default) is too low for local
        # models which routinely need 2-3 tries to produce schema-valid
        # JSON, especially in ``prompted`` output mode.
        _max_retries = getattr(
            getattr(agent, "runner", None), "max_validation_retries", None
        )
        if isinstance(_max_retries, int) and _max_retries > 0:
            agent_meta["output_retries"] = _max_retries

        return RenderedConfig(
            cwd=Path("."),
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
            async for ev in run_full_agent_mode(
                run_id=run_id,
                agent_module=agent_module,
                prompt=prompt,
                model_str=model_str,
                model=model,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                input_data=input_data,
                import_agent_fn=self._import_agent,
            ):
                yield ev
            return

        async for ev in run_direct_agent_mode(
            run_id=run_id,
            prompt=prompt,
            model_str=model_str,
            output_schema=output_schema,
            input_schema=rendered.agent_meta.get("input_schema"),
            output_mode=output_mode,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            output_retries=rendered.agent_meta.get("output_retries"),
            references=rendered.agent_meta.get("references") or [],
            input_data=input_data,
            host_env_grants=rendered.agent_meta.get("host_env_grants"),
            agent_tool_grants=(
                set(_atg)
                if (_atg := rendered.agent_meta.get("agent_tool_grants")) is not None
                else None
            ),
            workspace_id=rendered.agent_meta.get("host_env_workspace_id"),
            workdir=rendered.agent_meta.get("host_env_workdir"),
            db_path=rendered.agent_meta.get("host_env_db_path"),
        ):
            yield ev

    # --------------------------------------------------------------------------
    # Backward-compat staticmethod shims — the original class exposed these as
    # part of its public surface; keep them so any consumer that reached into
    # ``TokenBackend._import_agent`` etc. keeps working.
    # --------------------------------------------------------------------------

    @staticmethod
    def _import_agent(module_path: str) -> type:
        return import_agent(module_path)

    @staticmethod
    def _resolve_request_model(agent_cls: type) -> type:
        return resolve_request_model(agent_cls)

    @staticmethod
    def _auto_generate_agent(agent_id: str, system_prompt: str) -> type:
        """Dynamically create a pydantic-agents BaseAgent class from a markdown prompt.

        The generated agent:
        - Uses ``system_prompt`` as its system prompt.
        - Accepts ``dict[str, Any]`` as input.
        - Returns ``dict[str, Any]`` as output.
        - No custom tools.
        """
        try:
            pydantic_agents = __import__("pydantic_agents")
            BaseAgent = pydantic_agents.BaseAgent
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

        class _AutoGeneratedAgent(BaseAgent[_AutoRequest, _AutoResponse]):
            OUTPUT_TYPE = _AutoResponse
            _SYSTEM_PROMPT = system_prompt

            def build_system_prompt(self) -> str:
                return self._SYSTEM_PROMPT

        _AutoGeneratedAgent.__name__ = f"AutoAgent_{agent_id.replace('.', '_')}"
        return _AutoGeneratedAgent
