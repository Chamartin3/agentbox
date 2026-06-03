"""Pre-backend resource preparation, extracted from RunExecutor.execute().

This module owns the pre-backend orchestration block: workspace
resource materialization, env-doc rendering, subagent wiring, and
delegation to :func:`resolve_run_prompt` for the system-prompt
assembly pipeline (composition + binding substitution + output
contract + schema fallback + consistency check).

Contract:
- Pure-ish: reads from ``store``, the filesystem, and ``settings``; writes
  rendered files to ``workdir`` and stages CLAUDE.md / AGENTS.md / subagent
  files. Does *not* write to the SessionStore — snapshot persistence is the
  executor's job (it persists ``PreparedResources.resource_snapshot_entries``
  after the run row is created).
- Composed prompt/schema state is returned as a typed
  :class:`~agentbox.core.execution.prepare.prompts.ComposedState` on
  :attr:`PreparedResources.composed`. The executor threads it through
  ``render`` / ``validate_output`` / capture explicitly — there is no
  hidden ``agent.__dict__`` side-channel anymore.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.data import AgentDef
from agentbox.core.resource.subagent_render import materialize_subagents
from agentbox.core.resource.workspace_materialize import materialize_workspace
from agentbox.core.execution.prepare.prompts import ComposedState, resolve_run_prompt
from agentbox.core.execution.prepare.envdoc import (
    render_env_doc,
    resolve_workspace_resources,
    resolve_workspace_subagents,
    workspace_outcomes_to_snapshot,
)

if TYPE_CHECKING:
    from agentbox.config import Settings
    from agentbox.core.data import SessionStore

logger = logging.getLogger(__name__)


@dataclass
class PreparedResources:
    """Result of :func:`prepare_run_resources`.

    See :class:`agentbox.core.execution.prepare.prompts.ResolvedPrompt` for
    the prompt-assembly outputs that are surfaced through ``agent``.
    """

    agent: AgentDef
    input_: str
    composed: ComposedState
    resource_snapshot_entries: list[dict] = field(default_factory=list)
    prompt_bindings: list[dict] = field(default_factory=list)
    composed_result: Any = None
    workspace_id: str | None = None


def prepare_run_resources(
    *,
    store: SessionStore,
    settings: Settings,
    agent: AgentDef,
    input_: str,
    variables: dict[str, Any] | None,
    workdir: Path,
) -> PreparedResources:
    """Run the pre-backend prep pipeline."""
    resource_snapshot_entries: list[dict] = []
    workspace_id = agent.workspace if agent.workspace != "<ephemeral>" else None

    # ----- workspace resources, env doc, subagents ----------------------
    if workspace_id:
        try:
            ws_bindings = resolve_workspace_resources(store, workspace_id)
            if ws_bindings:
                outcomes = materialize_workspace(
                    workdir,
                    ws_bindings,
                    cache_root=settings.resource_cache_dir,
                )
                resource_snapshot_entries.extend(
                    workspace_outcomes_to_snapshot(outcomes)
                )
        except Exception:
            logger.exception(
                "executor: workspace resource materialization failed for workspace %r",
                workspace_id,
            )

        try:
            env_doc_entries = render_env_doc(store, workspace_id, workdir)
            resource_snapshot_entries.extend(env_doc_entries)
        except Exception:
            logger.exception(
                "executor: env doc rendering failed for workspace %r",
                workspace_id,
            )

        try:
            resolved_subagents = resolve_workspace_subagents(store, workspace_id)
            if resolved_subagents:
                sub_outcomes = materialize_subagents(workdir, resolved_subagents)
                for o in sub_outcomes:
                    resource_snapshot_entries.append(
                        {
                            "role": "workspace_subagent",
                            "workspace_id": o.workspace_id,
                            "agent_id": o.agent_id,
                            "alias": o.alias,
                            "files_written": o.files_written,
                        }
                    )
        except Exception:
            logger.exception(
                "executor: workspace subagent materialization failed for workspace %r",
                workspace_id,
            )

    # ----- unified prompt resolution -----------------------------------
    resolved = resolve_run_prompt(
        store=store,
        settings=settings,
        agent=agent,
        input_=input_,
        variables=variables,
    )
    agent = resolved.agent
    input_ = resolved.input_
    resource_snapshot_entries.extend(resolved.snapshot_entries)

    return PreparedResources(
        agent=agent,
        input_=input_,
        composed=resolved.to_composed_state(),
        resource_snapshot_entries=resource_snapshot_entries,
        prompt_bindings=resolved.prompt_bindings,
        composed_result=resolved.composition_result,
        workspace_id=workspace_id,
    )
