"""Run dispatch — create_run / rerun."""

from __future__ import annotations

import json as _json
import logging
from typing import TYPE_CHECKING, Any

from agentbox.core.service.agents import resolve_agent
from agentbox.core.service.execution.types import (
    AgentDisabled,
    InvalidRunInput,
    RunNotFound,
)
from agentbox.core.service.prompts import AgentNotFound


def _assert_enabled(store: "SessionStore", agent_id: str) -> None:
    if store.is_agent_disabled(agent_id):
        meta = store.get_agent_meta(agent_id) or {}
        raise AgentDisabled(agent_id, meta.get("disabled_at"))


if TYPE_CHECKING:
    from agentbox.core.db import SessionStore
    from agentbox.core.execution.orchestrate.executor import RunExecutor

logger = logging.getLogger(__name__)


async def create_run(
    agent_id: str,
    *,
    store: SessionStore,
    executor: RunExecutor,
    input_: str | None = None,
    variables: dict[str, str] | None = None,
    session_id: str | None = None,
    workspace: str | None = None,
    timeout_seconds: int | None = None,
    webhook_url: str | None = None,
    runner: str | None = None,
    backend: str | None = None,
    runner_profile: str | None = None,
    runner_config: dict[str, Any] | None = None,
    runner_embedded: bool = False,
) -> dict:
    """Validate input, resolve the agent, and dispatch to the executor.

    Raises :class:`AgentNotFound`, :class:`InvalidRunInput`, or
    :class:`NoBackendAvailable`. Returns ``{"run_id", "agent"}``.
    """
    agent = resolve_agent(agent_id, store=store)
    if agent is None:
        raise AgentNotFound(agent_id)
    _assert_enabled(store, agent.id)

    if input_ is not None and variables is None:
        if agent.composition is not None:
            logger.warning(
                "run for agent %r uses legacy 'input' but agent has [composition]; "
                "migrate to 'variables' with 'user_message'",
                agent.id,
            )
        run_id = await executor.execute(
            agent,
            input_,
            session_id=session_id,
            workspace_override=workspace,
            timeout_seconds=timeout_seconds,
            webhook_url=webhook_url,
            runner_override=runner,
            backend=backend,
            runner_profile=runner_profile,
            runner_config=runner_config,
        )
        return {"run_id": run_id, "agent": agent.id}

    if variables is None:
        raise InvalidRunInput("either 'input' or 'variables' must be provided")

    run_id = await executor.execute(
        agent,
        "",
        variables=variables,
        session_id=session_id,
        workspace_override=workspace,
        timeout_seconds=timeout_seconds,
        webhook_url=webhook_url,
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
    store: SessionStore,
    executor: RunExecutor,
) -> dict:
    """Re-execute a finished run with the same agent + input/variables."""
    rec = store.get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    agent = resolve_agent(rec.agent_id, store=store)
    if agent is None:
        raise AgentNotFound(rec.agent_id)
    _assert_enabled(store, agent.id)

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

    new_id = await executor.execute(
        agent,
        rec.input or "",
        variables=variables,
        session_id=None,
        workspace_override=None,
    )
    return {"run_id": new_id, "agent": agent.id, "rerun_of": run_id}
