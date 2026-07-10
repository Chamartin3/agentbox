"""Canonical → backend-native tool name translation.

This module owns the translation *algorithm* and the effective-tool
intersection helper.  It must stay agnostic: it does not import any
backend and depends solely on ``CanonicalTool``.

Per-backend native-name maps live in
``agentbox.core.engines.backends.<be>.tools`` and are passed into
:func:`translate_tool` by the consumer that knows which backend it is
targeting.
"""

from __future__ import annotations

from collections.abc import Collection

from agentbox.core.tools.canonical import CanonicalTool


def _target_mcp_prefix(
    mcp_prefixes: dict[str, str] | None,
    source_name: str | None = None,
) -> str | None:
    """Pick the target MCP prefix from *mcp_prefixes*.

    If *source_name* starts with one of the source prefixes, return the
    matching target prefix. Otherwise return the first target prefix.
    Returns ``None`` when no prefixes are available.
    """
    if not mcp_prefixes:
        return None
    if source_name is not None:
        for source_prefix, target_prefix in mcp_prefixes.items():
            if source_name.startswith(source_prefix):
                return target_prefix
    return next(iter(mcp_prefixes.values()))


def translate_tool(
    name: str,
    native_map: dict[CanonicalTool, str],
    *,
    mcp_prefixes: dict[str, str] | None = None,
) -> str:
    """Translate any tool name into the target backend's native vocabulary.

    *native_map* is a ``CanonicalTool`` → native-name mapping owned by
    the target backend (e.g. ``claude_code.tools.NATIVE_TOOLS``).

    Resolution order:

    1. *name* is already a canonical tool → direct lookup in
       *native_map*.  If the canonical tool has no native mapping the
       env‑MCP fallback is used (gap coverage).
    2. *name* is a native tool of the target backend (appears as a
       value in *native_map*) → returned unchanged (idempotent).
    3. *name* carries an MCP prefix that appears in *mcp_prefixes* →
       the prefix is rewritten.
    4. Unknown → passthrough unchanged.
    """
    # 1 – canonical tool?
    try:
        tool = CanonicalTool(name)
    except ValueError:
        pass
    else:
        if tool in native_map:
            return native_map[tool]
        # Gap coverage: canonical tool, no native mapping.
        target_prefix = _target_mcp_prefix(mcp_prefixes)
        if target_prefix is not None:
            return f"{target_prefix}{name}"
        return name

    # 2 – already a native name of the target backend?
    for native in native_map.values():
        if native == name:
            return name

    # 3 – MCP prefix rewrite?
    if mcp_prefixes:
        for source_prefix, target_prefix in mcp_prefixes.items():
            if name.startswith(source_prefix):
                return f"{target_prefix}{name[len(source_prefix):]}"

    # 4 – passthrough
    return name


def intersect_allowed_tools(
    agent_tools: set[CanonicalTool],
    workspace_tools: set[CanonicalTool] | None,
) -> set[CanonicalTool]:
    """Effective allow list = agent ∩ workspace.

    If either side is empty/None, treat it as "no restriction" so the
    other side governs alone.  Returns the set of canonical tools that
    are authorized by the agent AND available in the workspace.
    """
    if not agent_tools and not workspace_tools:
        return set()
    if not agent_tools:
        return set(workspace_tools or set())
    if not workspace_tools:
        return set(agent_tools)
    return agent_tools & workspace_tools


def effective_tool_set(
    *,
    allowed: Collection[str],
    forbidden: Collection[str],
    available: Collection[str],
) -> set[str]:
    """The single tool-authorization formula (works on tool-name strings).

        base      = available                if allowed is empty
                  = allowed ∩ available       otherwise
        effective = base − forbidden

    ``available`` is the concrete availability surface (engine native
    built-ins ∪ workspace catalog). Names are plain strings so MCP/resource
    tools — which are not ``CanonicalTool`` members — pass through; the
    allow/deny lists hold canonical names (a subset). ``forbidden`` entries
    absent from ``available`` are simply a no-op.
    """
    a, f, av = set(allowed), set(forbidden), set(available)
    base = av if not a else (a & av)
    return base - f
