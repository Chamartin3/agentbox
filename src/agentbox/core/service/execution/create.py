"""Run dispatch — create_run / rerun."""

from __future__ import annotations

import json as _json
import logging

from agentbox.core.agents import build_prompt
from agentbox.core.db import AgentDefManager, AgentMetaManager
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.service.agents.crud import resolve_agent
from agentbox.core.data.payload_types import RunCreatedResult, RerunResult
from agentbox.core.service.execution.service import ExecutionService
from agentbox.core.service.execution.types import (
    AgentDisabled,
    InvalidRunInput,
    RunNotFound,
)
from agentbox.core.service.agents.prompts import AgentNotFound


def _svc() -> ExecutionService:
    return ExecutionService()


def _assert_enabled(agent_meta: AgentMetaManager, agent_id: str) -> None:
    meta = agent_meta.get_meta(agent_id)
    if meta and meta.get("disabled_at"):
        raise AgentDisabled(agent_id, meta.get("disabled_at"))


logger = logging.getLogger(__name__)


async def create_run(
    agent_id: str,
    *,
    agent_defs: "AgentDefManager",
    agent_meta: "AgentMetaManager",
    executor: "RunExecutor",
    input_: str | None = None,
    variables: dict[str, str] | None = None,
    session_id: str | None = None,
    workspace: str | None = None,
    timeout_seconds: int | None = None,
    webhook_url: str | None = None,
    runner: str | None = None,
    backend: str | None = None,
    runner_profile: str | None = None,
    runner_config: dict | None = None,
    runner_embedded: bool = False,
) -> RunCreatedResult:
    """Validate input, resolve the agent, and dispatch to the executor.

    Raises :class:`AgentNotFound`, :class:`InvalidRunInput`, or
    :class:`NoBackendAvailable`. Returns ``{"run_id", "agent"}``.
    """
    agent = resolve_agent(agent_id, agent_defs=agent_defs)
    if agent is None:
        raise AgentNotFound(agent_id)
    _assert_enabled(agent_meta, agent.id)

    if input_ is not None and variables is None:
        if agent.composition is not None:
            logger.warning(
                "run for agent %r uses legacy 'input' but agent has [composition]; "
                "migrate to 'variables' with 'user_message'",
                agent.id,
            )
        if webhook_url is not None:
            agent = agent.model_copy(update={"webhook_url": webhook_url})
        composed = build_prompt(
            db=executor.db,
            settings=executor.settings,
            agent=agent,
            input_=input_,
            variables=None,
        )
        run_id = await executor.execute(
            composed,
            variables=None,
            session_id=session_id,
            workspace_override=workspace,
            timeout_seconds=timeout_seconds,
            runner_override=runner,
            backend=backend,
            runner_profile=runner_profile,
            runner_config=runner_config,
        )
        return {"run_id": run_id, "agent": agent.id}

    if variables is None:
        raise InvalidRunInput("either 'input' or 'variables' must be provided")

    if webhook_url is not None:
        agent = agent.model_copy(update={"webhook_url": webhook_url})
    composed = build_prompt(
        db=executor.db,
        settings=executor.settings,
        agent=agent,
        input_="",
        variables=variables,
    )
    run_id = await executor.execute(
        composed,
        variables=variables,
        session_id=session_id,
        workspace_override=workspace,
        timeout_seconds=timeout_seconds,
        runner_override=runner,
        backend=backend,
        runner_profile=runner_profile,
        runner_config=runner_config,
        runner_embedded=runner_embedded,
    )
    return {"run_id": run_id, "agent": agent.id}


async def rerun(
    run_id: str,
    *,
    agent_defs: "AgentDefManager",
    agent_meta: "AgentMetaManager",
    executor: "RunExecutor",
) -> RerunResult:
    """Re-execute a finished run with the same agent + input/variables."""
    rec = _svc().get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    agent = resolve_agent(rec.agent_id, agent_defs=agent_defs)
    if agent is None:
        raise AgentNotFound(rec.agent_id)
    _assert_enabled(agent_meta, agent.id)

    variables: dict[str, str] | None = None
    if rec.variables:
        try:
            parsed = (
                _json.loads(rec.variables)
                if isinstance(rec.variables, str)
                else rec.variables
            )
            if isinstance(parsed, dict):
                variables = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            variables = None

    composed = build_prompt(
        db=executor.db,
        settings=executor.settings,
        agent=agent,
        input_=rec.input or "",
        variables=variables,
    )
    new_id = await executor.execute(
        composed,
        variables=variables,
        session_id=None,
        workspace_override=None,
    )
    return {"run_id": new_id, "agent": agent.id, "rerun_of": run_id}
