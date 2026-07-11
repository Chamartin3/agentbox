"""Agent tool authorization: default-grant-all with a forbidden deny-list.

Implements the "agent chooses" term of the authorization model — given the
availability surface the workspace exposes, decide which tools the agent may
actually use:

    base      = available                if allowed_tools is empty
              = allowed_tools ∩ available  otherwise
    effective = base − forbidden_tools

The set math lives once in :func:`core.tools.translation.effective_tool_set`;
this module wraps it in the agent-facing ``ToolInfo`` presentation. It does
NOT resolve the workspace catalog itself — agents and workspaces are
independent peers (import-linter ``agents-peer``), so the caller (execution
setup / service, which may see both domains) resolves ``available`` and passes
it in.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from agentbox.core.agents.definition.config import RuntimeConfig
from agentbox.core.data import AgentDef
from agentbox.core.data.payload_types import ToolInfo
from agentbox.core.data import CanonicalTool
from agentbox.core.tools.translation import effective_tool_set

logger = logging.getLogger(__name__)


def available_tools(
    native: Sequence[CanonicalTool],
    workspace_catalog: Sequence[ToolInfo] = (),
) -> list[ToolInfo]:
    """Union of the engine's native built-ins and the workspace catalog.

    ``native`` are the backend's canonical built-in tools; ``workspace_catalog``
    is the resolved availability surface from the workspace (built by the
    caller). Union by name; workspace entries win on collisions because they
    carry richer ``source``/``native`` detail. Sorted by name for a stable
    surface.
    """
    by_name: dict[str, ToolInfo] = {
        str(c): ToolInfo(name=str(c), source="builtin", native=None) for c in native
    }
    for item in workspace_catalog:
        by_name[item["name"]] = item
    return [by_name[k] for k in sorted(by_name)]


def effective_tools(
    agent: AgentDef,
    available: Sequence[ToolInfo],
) -> list[ToolInfo]:
    """Filter ``available`` down to what ``agent`` may actually use.

    Reads the agent's ``allowed_tools`` / ``forbidden_tools`` (canonical) from
    its runtime config and applies :func:`effective_tool_set`. Forbidden names
    absent from ``available`` are a logged no-op (they subtract nothing).
    """
    rc = RuntimeConfig.from_agent(agent)
    avail_names = {t["name"] for t in available}
    for f in rc.forbidden_tools:
        if str(f) not in avail_names:
            logger.info(
                "agent %s forbids %r which is not in its available tools — no-op",
                getattr(agent, "id", "?"),
                str(f),
            )
    keep = effective_tool_set(
        allowed=rc.allowed_tools,
        forbidden=rc.forbidden_tools,
        available=avail_names,
    )
    return [t for t in available if t["name"] in keep]
