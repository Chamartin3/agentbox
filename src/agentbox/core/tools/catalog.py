"""Callable-item type and enumeration — the unit of workspace-tool authorisation.

``CallableItem`` is the common type that every source (MCP, guardrails /
host-env, resource bindings) expresses its tools in.  The API endpoint
and the executor each gather the per-source slices and flatten + deduplicate
them via :func:`enumerate_callables`.

Tools never imports workspaces, resources, or the MCP registry.  Sources
push their slices in; this module owns only the type and the algebra.
"""

from __future__ import annotations
from typing import Any

import logging
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CallableItem:
    """One callable item — a tool, capability, or resource binding.

    Every source produces these; ``enumerate_callables`` flattens a list
    of source-slices into a single deduplicated list.

    Fields mirror the workspace-catalog shape so that sources can be
    round-tripped through the API without mapping.
    """

    name: str
    kind: str  # "mcp" | "host_env" | "resource"
    description: str = ""
    server: str | None = None
    input_schema: dict[str, Any] | None = None
    policy: dict[str, Any] | None = field(default_factory=dict)
    """Grant-param payload for host-env capabilities."""


def enumerate_callables(
    slices: list[list[CallableItem]],
) -> list[CallableItem]:
    """Flatten multiple source-slices and de-duplicate by ``name``.

    On collision the *first* occurrence wins and a debug-level log is
    emitted for the dropped duplicate.  This ensures canonical tools
    that appear in multiple sources are listed once.
    """
    seen: set[str] = set()
    result: list[CallableItem] = []
    for chunk in slices:
        for item in chunk:
            if item.name in seen:
                logging.getLogger(__name__).debug(
                    "enumerate_callables: dropping duplicate %r (kind=%s)",
                    item.name,
                    item.kind,
                )
                continue
            seen.add(item.name)
            result.append(item)
    return result
