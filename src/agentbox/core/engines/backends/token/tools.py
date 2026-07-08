"""Native in-process host-env tools for the token backend's direct path.

The other backends (claude_code, codex, opencode, pi) reach ``fs.read`` /
``fs.list`` through the stdio host-env MCP server injected into ``.mcp.json``.
The token *direct* path talks raw OpenAI-compatible HTTP to the model
(pydantic-ai → Ollama / OpenRouter / …) and never reads ``.mcp.json``, so those
tools were never presented to the model — it had nothing to call and could only
hallucinate file contents. This module rebuilds the same capabilities as
in-process pydantic-ai tool callables, enforced by the *same*
:func:`check_capability` grant logic, so direct-mode agents can actually invoke
them.

ponytail: in-process functions, not a spawned MCP subprocess. The path-scoping
enforcement (check_capability) is identical; what we skip is the audit-log DB
write the stdio server does, so direct-mode fs calls won't show in
``list_host_env_calls``. Add an audit hook here if that audit trail is needed
for the token backend too.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

from agentbox.core.data.constants import HOST_ENV_SERVER_NAME
from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.mcp_servers.specs import host_env_server_spec
from agentbox.core.tools.grants import GrantViolation, check_capability

logger = logging.getLogger(__name__)


def _coerce_to_text(result: Any) -> str:
    """Flatten an MCP tool result to a string for Ollama compatibility.

    Ollama's OpenAI-compat endpoint 400s on array/object tool-result content.
    Handles plain str/list/dict and MCP text-content objects (``.text``).
    """
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return json.dumps(result, default=str)
    if isinstance(result, (list, tuple)):
        parts: list[str] = []
        for item in result:
            if isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(str(item.text))
            else:
                parts.append(_coerce_to_text(item))
        return "\n".join(parts)
    if hasattr(result, "text"):
        return str(result.text)
    return str(result)


async def _stringify_tool_result(ctx: Any, call_tool: Any, name: str, tool_args: dict) -> str:
    """``process_tool_call`` hook: run the MCP tool, return its result as text."""
    return _coerce_to_text(await call_tool(name, tool_args))


def build_host_env_toolsets(
    host_env_grants: dict[str, Any] | None,
    workspace_id: str | None,
    workdir: str | Path | None,
    db_path: str | Path | None,
) -> list[MCPToolset]:
    """Connect to the host-env stdio MCP server as pydantic-ai toolset(s).

    This is the parity path: it spawns the *same* host-env server (same spec as
    the .mcp.json injection that MCP-aware backends use), so the token backend
    presents the identical, grant-enforced tool surface as every other backend
    — a single source of tool definitions, no reimplementation.

    Returns ``[]`` (caller falls back to :func:`build_host_env_tools`) when
    there are no grants or pydantic-ai's MCP support is unavailable.

    Two Ollama-compat shims vs. the stock ``load_mcp_toolsets``:

    * **No server-name prefix.** ``load_mcp_toolsets`` wraps each server in a
      ``PrefixedToolset`` (``agentbox-host-env_fs.list``); the long name
      suppresses tool calls on local models. We build ``MCPToolset`` directly
      so the tool keeps its bare canonical name (``fs.list``).
    * **String-coerced results.** Ollama's OpenAI-compat endpoint 400s when a
      tool result serializes as a JSON array/object (``fs.list`` → ``list``,
      ``workspace_info`` → ``dict``). A ``process_tool_call`` hook stringifies
      any non-string result before it goes back to the model.
    """
    if not host_env_grants:
        return []
    if os.environ.get("AGENTBOX_TOKEN_MCP_TOOLS", "1") == "0":
        return []  # kill-switch: force the in-process fallback
    try:
        spec = host_env_server_spec(
            grants=host_env_grants,
            workspace_id=workspace_id or "",
            workdir=Path(workdir) if workdir else Path("."),
            db_path=Path(db_path) if db_path else Path("/data/agentbox.sqlite"),
        )
        # The spawned subprocess needs the ambient environment (PATH, venv,
        # PYTHONPATH) on top of the grant/context vars. The .mcp.json consumer
        # (Claude) merges with the process env itself; pydantic-ai's stdio
        # transport does not, so merge here.
        env = {**os.environ, **spec["env"]}
        transport = StdioTransport(
            command=spec["command"], args=list(spec["args"]), env=env
        )
        toolset = MCPToolset(
            transport,
            id=HOST_ENV_SERVER_NAME,
            process_tool_call=_stringify_tool_result,
        )
        return [toolset]
    except Exception:
        logger.warning(
            "token backend: could not build host-env MCP toolset; "
            "falling back to in-process fs tools",
            exc_info=True,
        )
        return []


def build_host_env_tools(
    host_env_grants: dict[str, Any] | None,
    agent_tool_grants: set[str] | None = None,
) -> list[Callable[..., Any]]:
    """Return pydantic-ai tool callables for the fs capabilities the agent may use.

    A tool is built only when it is BOTH allowed by the workspace host-env
    (present in ``host_env_grants`` with ``allowed_paths``) AND granted to the
    agent (``agent_tool_grants``; ``None`` means "no agent-level restriction",
    mirroring :func:`intersect_allowed_tools`).

    Denials and IO errors are returned to the model as an ``ERROR: ...`` string
    rather than raised, so the run completes and the model can surface the
    refusal. The grant check runs *before* any filesystem access, so an
    out-of-scope path never reads/lists anything.
    """
    grants = host_env_grants or {}
    if not grants:
        return []

    def _allowed(name: str) -> bool:
        in_workspace = name in grants
        in_agent = agent_tool_grants is None or name in agent_tool_grants
        return in_workspace and in_agent

    tools: list[Callable[..., Any]] = []

    if _allowed(CanonicalTool.FS_READ.value):

        def fs_read(path: str) -> str:
            """Read a UTF-8 text file and return its contents.

            ``path`` must resolve inside one of the directories the workspace
            grants access to; otherwise an error string is returned.
            """
            try:
                check_capability(grants, CanonicalTool.FS_READ, {"path": path})
            except GrantViolation as exc:
                return f"ERROR: {exc}"
            try:
                return Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return f"ERROR: {exc}"

        tools.append(fs_read)

    if _allowed(CanonicalTool.FS_LIST.value):

        def fs_list(path: str) -> str:
            """List the entries of a directory, one per line.

            ``path`` must resolve inside one of the directories the workspace
            grants access to; otherwise an ``ERROR: ...`` string is returned.
            """
            # Returns a newline-joined string, not list[str]: Ollama's
            # OpenAI-compatible endpoint 400s ("invalid message content type:
            # <nil>") when a tool result is serialized as a JSON array. A
            # string tool result is portable across every provider.
            try:
                check_capability(grants, CanonicalTool.FS_LIST, {"path": path})
            except GrantViolation as exc:
                return f"ERROR: {exc}"
            try:
                return "\n".join(sorted(str(e) for e in Path(path).iterdir()))
            except OSError as exc:
                return f"ERROR: {exc}"

        tools.append(fs_list)

    return tools
