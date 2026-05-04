"""Token runner — runs a pydantic-ai Agent in-process (legacy Runner interface).

Two modes:

1. **Full agent** — ``agent_module`` is set on the ``RunnerSpec``
   (e.g. ``agents.company_researcher.agent:CompanyResearcherAgent``).
   The runner imports the class, instantiates it, and calls
   ``agent.run(input_model)``.

2. **Auto-generated** — only ``prompt_path`` is provided on the
   ``AgentDef``. The runner dynamically creates a minimal pydantic-ai
   Agent that uses the markdown as its system prompt, takes a
   ``dict[str, Any]`` as input, and returns ``dict[str, Any]`` as
   output.

Input:
  The executor passes ``req.input`` as a JSON string. For typed agents
  this is deserialized into the agent's request model. For auto-generated
  agents it is passed as a ``dict``.

Output:
  The agent's return value is serialized to JSON and yielded as a
  ``TextEvent``. Usage statistics are yielded as ``UsageEvent``.
  Completion is signaled via ``DoneEvent``.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from typing import Any

from agentbox.api.events import DoneEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.runners.base import Runner, RunRequest


class TokenRunner(Runner):
    kind = "token"
    conversation_format = "pydantic-ai-history"

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        spec = req.agent.runner

        # Resolve the agent class.
        if spec.agent_module:
            agent_cls = self._import_agent(spec.agent_module)
        else:
            # Auto-generate from markdown prompt.
            prompt = req.agent.load_prompt(req.project_root)
            agent_cls = self._auto_generate_agent(req.agent.id, prompt)

        # Parse input as JSON.
        try:
            input_data = json.loads(req.input) if req.input else {}
        except json.JSONDecodeError as exc:
            yield DoneEvent(
                run_id=req.run_id, ok=False, error=f"invalid input JSON: {exc}"
            )
            return

        # Build the request model.
        request_model = self._resolve_request_model(agent_cls)
        try:
            request = request_model.model_validate(input_data)
        except Exception as exc:
            yield DoneEvent(
                run_id=req.run_id,
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
                run_id=req.run_id,
                ok=False,
                error=f"agent instantiation error: {exc}",
            )
            return

        # Run the agent synchronously (pydantic-ai's _run_sync is sync).
        start = time.monotonic()
        try:
            result = agent.run_sync(request)
        except Exception as exc:
            yield DoneEvent(
                run_id=req.run_id,
                ok=False,
                error=f"agent execution error: {exc}",
            )
            return
        _elapsed = time.monotonic() - start

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
                run_id=req.run_id,
                ok=False,
                error=f"output serialization error: {exc}",
            )
            return

        yield TextEvent(run_id=req.run_id, text=output_text)

        # Estimate usage (pydantic-ai doesn't expose token counts
        # directly from _run_sync).
        yield UsageEvent(
            run_id=req.run_id,
            input_tokens=0,
            output_tokens=0,
            cost_usd=None,
            model=getattr(agent, "model", None),
        )

        yield DoneEvent(run_id=req.run_id, ok=True)

    # ------------------------------------------------------------------
    # Import helpers
    # ------------------------------------------------------------------

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
            # Also add common project subdirectories so library
            # packages (e.g. ``libs/pydantic_agents/``) are findable.
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
        # Check common patterns:
        # 1. BaseAgent[RequestModel, ResponseModel] — extract from __orig_bases__
        # 2. Agent class with an explicit INPUT_TYPE attribute
        # 3. Fall back to dict[str, Any]

        if hasattr(agent_cls, "INPUT_TYPE") and agent_cls.INPUT_TYPE is not None:
            return agent_cls.INPUT_TYPE

        # Try to extract from generic base.
        for base in getattr(agent_cls, "__orig_bases__", []):
            args = getattr(base, "__args__", [])
            if args:
                return args[0]

        # Fallback: accept any dict.
        from pydantic import BaseModel, Field

        class _GenericInput(BaseModel):
            data: dict[str, Any] = Field(default_factory=dict)

        return _GenericInput

    # ------------------------------------------------------------------
    # Auto-generation for markdown-only agents
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_generate_agent(agent_id: str, system_prompt: str) -> type:
        """Dynamically create a pydantic-ai Agent class from a markdown prompt.

        The generated agent:
        - Uses ``system_prompt`` as its system prompt.
        - Accepts ``dict[str, Any]`` as input.
        - Returns ``dict[str, Any]`` as output.
        - No custom tools.
        """
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
