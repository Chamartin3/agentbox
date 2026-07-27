"""Shared MCP launch-command resolution — single source of truth for both
the config-file path (``.mcp.json`` / ``opencode.json``) and the token
in-process path (pydantic-ai ``StdioTransport``).

Every backend that spawns an MCP server resolves its command through
:func:`resolve_mcp_launch_command` so both paths launch the same binary
for the same server spec.

Ponytail: the mapping table is explicit, not a plugin system. Add a row
when a new pinned server is introduced.
"""
from __future__ import annotations

import shutil
from typing import TypedDict

# ── Installed-server mapping ──────────────────────────────────────────
#
# When ``uvx`` is not available in the container, a pinned ``uvx <pkg>``
# spec is resolved to ``python3 -m <module>`` using this table.  Keys
# are the package name (the first positional arg after ``uvx``); values
# are the Python module name.
#
# Extend this table when a new pinned MCP server is added.  Once ``uvx``
# is baked into the image (Phase 3), this mapping becomes a fallback.
# ----------------------------------------------------------------------

_UVX_FALLBACK: dict[str, str] = {
    "mcp-server-time": "mcp_server_time",
}


class LaunchCommand(TypedDict):
    """Resolved launch command for an MCP server."""
    command: str
    args: list[str]
    env: dict[str, str]


def resolve_mcp_launch_command(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
) -> LaunchCommand:
    """Resolve an MCP server's argv into a concrete ``command`` + ``args``.

    *argv* is the full list (e.g. ``["uvx", "mcp-server-time"]`` or
    ``["python3", "-m", "mcp_server_time"]``).  Returns a
    :class:`LaunchCommand` with the head separated from the tail and any
    known fallback applied.

    Mapping rules (in order):

    1. ``uvx <pkg> [args...]`` — if ``uvx`` **is** on PATH, passthrough.
       Otherwise, map to ``python3 -m <module> [args...]`` using the
       explicit fallback table. If the package is not in the table, raise
       :class:`ValueError`.

    2. Everything else (``npx``, ``python3``, bare commands) — passthrough
       with the head/tail split unchanged.
    """
    if not argv:
        raise ValueError("empty command list")

    head, tail = argv[0], list(argv[1:])
    cmd_env = dict(env) if env else {}

    if head == "uvx":
        if shutil.which("uvx"):
            return LaunchCommand(command=head, args=tail, env=cmd_env)
        # uvx not available — consult the fallback table.
        if not tail:
            raise ValueError("uvx command has no package argument")
        pkg = tail[0]
        module = _UVX_FALLBACK.get(pkg)
        if module is None:
            raise ValueError(
                f"uvx is not installed and no fallback is known for "
                f"package {pkg!r}. Install uv/uvx in the container or add "
                f"a fallback entry for {pkg!r}."
            )
        return LaunchCommand(
            command="python3",
            args=["-m", module, *tail[1:]],
            env=cmd_env,
        )

    # Passthrough: npx, python3, bare commands — just split.
    return LaunchCommand(command=head, args=tail, env=cmd_env)
