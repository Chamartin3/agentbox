"""Backend adapter for the PydanticAI in-process runner.

``render()`` extracts agent metadata (agent_module, prompt) from the
``AgentDef`` and stores it in ``RenderedConfig.agent_meta``.
``run()`` runs the agent in-process using the stored metadata.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.backends.base import BackendAdapter, RenderedConfig

_NAME = "pydantic_ai"


class PydanticAiBackend(BackendAdapter):
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
    ) -> RenderedConfig:
        spec = agent.runner
        model = self._resolve_model(spec)
        agent_meta: dict[str, Any] = {
            "agent_module": spec.agent_module,
            "prompt": self._resolve_prompt(agent, workdir),
            "agent_id": agent.id,
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
        agent_module = rendered.agent_meta.get("agent_module")
        prompt = rendered.agent_meta.get("prompt", "")

        yield LogEvent(
            run_id=run_id,
            message="pydantic_ai backend: running agent in-process",
        )

        # Resolve the agent class.
        if agent_module:
            agent_cls = self._import_agent(agent_module)
        else:
            agent_id = rendered.agent_meta.get("agent_id", "auto")
            agent_cls = self._auto_generate_agent(agent_id, prompt)

        # Parse input as JSON.
        try:
            input_data = json.loads(input) if input else {}
        except json.JSONDecodeError as exc:
            yield DoneEvent(run_id=run_id, ok=False, error=f"invalid input JSON: {exc}")
            return

        # Build the request model.
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
            agent = agent_cls(mcp_url=mcp_url)
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
            result = agent.run_sync(request)
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
            model=getattr(agent, "model", None),
        )

        yield DoneEvent(run_id=run_id, ok=True)

    # ------------------------------------------------------------------
    # Import helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _import_agent(module_path: str) -> type:
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
        if hasattr(agent_cls, "INPUT_TYPE") and agent_cls.INPUT_TYPE is not None:
            return agent_cls.INPUT_TYPE

        for base in getattr(agent_cls, "__orig_bases__", []):
            args = getattr(base, "__args__", [])
            if args:
                return args[0]

        from pydantic import BaseModel, Field

        class _GenericInput(BaseModel):
            data: dict[str, Any] = Field(default_factory=dict)

        return _GenericInput

    @staticmethod
    def _auto_generate_agent(agent_id: str, system_prompt: str) -> type:
        from pydantic import BaseModel, Field

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

        class _AutoGeneratedAgent(BaseAgent[_AutoRequest, _AutoResponse]):
            OUTPUT_TYPE = _AutoResponse
            _SYSTEM_PROMPT = system_prompt

            def build_system_prompt(self) -> str:
                return self._SYSTEM_PROMPT

        _AutoGeneratedAgent.__name__ = f"AutoAgent_{agent_id.replace('.', '_')}"
        return _AutoGeneratedAgent
