"""Codex native MCP config serializer.

Codex (≥ 0.146) supports MCP servers via ``-c`` flags that override
``~/.codex/config.toml`` on a per-invocation basis.  Config keys follow
the ``[mcp_servers.<name>]`` TOML table shape:

  Stdio  → ``mcp_servers.<name>.command="..."``
           ``mcp_servers.<name>.args=[...]``
  HTTP   → ``mcp_servers.<name>.url="..."``

There is **no** per-server tool allow-list in the codex config schema
(confirmed against codex 0.146.0).  Tool-level scoping is handled at
the global ``--allowedTools`` level in the adapter, not here.

Phase 0 findings (verified 2026-07-31):

- ``codex mcp add test -- <command>`` writes:
    [mcp_servers.test]
    command = "<command>"
    args = [...]
- ``codex mcp add test --url <url>`` writes:
    [mcp_servers.test]
    url = "<url>"
- The TOML value is parsed by codex itself; passing JSON-encoded TOML
  via ``-c`` lets us inject per-server config without touching the user's
  global ``~/.codex/config.toml``.
"""

from __future__ import annotations

from agentbox.core.data.payload_types import AgentMetaDict, ExternalMcpServer, McpServerConfig, McpStdioServerSpec
from agentbox.core.workspaces.tooling.launch import resolve_mcp_launch_command


def _toml_string(s: str) -> str:
    """Encode *s* as a TOML basic string literal (double-quoted, escaped)."""
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _toml_array(items: list[str]) -> str:
    """Encode a list of strings as a TOML inline array."""
    return "[" + ", ".join(_toml_string(i) for i in items) + "]"


def build_codex_mcp_argv(
    external_mcp_servers: list[ExternalMcpServer],
) -> list[str]:
    """Return ``codex exec -c …`` flags that inject *external_mcp_servers*.

    Each entry in *external_mcp_servers* must follow the shape produced by
    the executor's MCP-resolution block::

        {
            "name":          str,
            "config":        {"url": str} | {"command": list[str], "transport": str, ...},
            "disabled_tools": list[str],
        }

    The function converts each server to one or two ``-c`` flags:

    - Stdio servers:
        ``-c 'mcp_servers.<name>.command="<cmd>"'``
        ``-c 'mcp_servers.<name>.args=["<arg1>", ...]'``  (omitted when empty)
    - HTTP/SSE servers:
        ``-c 'mcp_servers.<name>.url="<url>"'``

    Tool scoping (``disabled_tools``) is NOT encoded here — codex has no
    per-server allow-list.  The global ``--allowedTools`` flag in the
    adapter handles canonical-tool filtering.

    Returns a flat list of ``["-c", "<key>=<toml_value>", ...]`` flags
    ready to be appended to the ``codex exec`` argv.
    """
    flags: list[str] = []

    for srv in external_mcp_servers:
        name = srv.get("name")
        config: McpServerConfig = srv.get("config") or {}

        if not isinstance(name, str) or not name:
            continue

        url = config.get("url")
        command_raw = config.get("command")

        if url and isinstance(url, str):
            # HTTP / SSE server.
            flags += ["-c", f"mcp_servers.{name}.url={_toml_string(url)}"]

        elif command_raw:
            # Stdio server — resolve through the shared launcher to handle
            # the uvx → python3 fallback.
            argv_list: list[str] = (
                list(command_raw) if isinstance(command_raw, list) else [str(command_raw)]
            )
            env_raw: dict[str, str] = config.get("env") or {}
            env: dict[str, str] = (
                {k: str(v) for k, v in env_raw.items()}
                if isinstance(env_raw, dict)
                else {}
            )
            try:
                launched = resolve_mcp_launch_command(argv_list, env=env)
            except ValueError:
                # Unknown command — skip rather than crash the run.
                continue

            cmd_val = _toml_string(launched["command"])
            flags += ["-c", f"mcp_servers.{name}.command={cmd_val}"]

            if launched["args"]:
                args_val = _toml_array(launched["args"])
                flags += ["-c", f"mcp_servers.{name}.args={args_val}"]

    return flags


def build_codex_intrinsic_mcp_argv(
    extra_mcp_servers: dict[str, McpStdioServerSpec],
) -> list[str]:
    """Convert intrinsic MCP server specs (host_env, agent_tools) to -c flags.

    *extra_mcp_servers* maps server-name → McpStdioServerSpec dict with
    ``command`` / ``args`` keys (the shape stored in ``agent_meta``'s
    ``host_env_*`` block is already resolved; here we just need the argv).

    Returns the same ``[-c, key=toml_value, ...]`` format as
    :func:`build_codex_mcp_argv`.
    """
    flags: list[str] = []
    for name, spec in extra_mcp_servers.items():
        if not isinstance(name, str) or not name:
            continue

        cmd = spec.get("command")
        args = spec.get("args") or []

        if not cmd:
            continue

        cmd_val = _toml_string(str(cmd))
        flags += ["-c", f"mcp_servers.{name}.command={cmd_val}"]

        args_list: list[str] = [str(a) for a in args] if args else []
        if args_list:
            args_val = _toml_array(args_list)
            flags += ["-c", f"mcp_servers.{name}.args={args_val}"]

    return flags


def mcp_flags_from_agent_meta(agent_meta: AgentMetaDict) -> list[str]:
    """Extract external-server MCP ``-c`` flags from a rendered ``agent_meta`` dict.

    Handles only external (project/workspace-attached) servers from
    ``external_mcp_servers``.  Intrinsic servers (``host_env``,
    ``agent_tools``) are handled separately in the adapter's ``run()``
    method via :func:`build_codex_intrinsic_mcp_argv`, which re-resolves
    their spawn specs from the raw grant inputs stored in ``agent_meta``
    (``host_env_grants``, ``host_env_db_path``, etc.).

    Returns a flat list of ``["-c", "<key>=<toml_value>", ...]`` flags
    ready to append to the ``codex exec`` argv.
    """
    flags: list[str] = []

    # External (project/workspace-attached) servers.
    external = agent_meta.get("external_mcp_servers")
    if external and isinstance(external, list):
        flags += build_codex_mcp_argv(external)

    return flags


# ---------------------------------------------------------------------------
# Codec-specific TOML escaping is tested independently in
# tests/unit/core/engines/backends/test_codex_mcp.py.
# ---------------------------------------------------------------------------
