"""Claude MCP config builder."""

from __future__ import annotations

from .schemas import ClaudeMcpConfig


def _claude_mcp_entry(
    url: str | None, transport: str, command: list[str] | None
) -> dict[str, object]:
    if url:
        return {"type": transport, "url": url}
    assert command, "mcp server needs url or command"
    return {"command": command[0], "args": list(command[1:])}


def build_claude_mcp_config(
    servers: list[dict] | None = None,
    *,
    mcp_server_name: str | None = None,
    mcp_url: str | None = None,
    mcp_transport: str = "http",
    mcp_command: list[str] | None = None,
) -> dict[str, dict[str, object]]:
    """Claude Code ``--mcp-config`` payload.

    Pass ``servers`` (list of ``{name,url,transport,command}``) for the
    multi-server form. Single-server kwargs are kept for back-compat with
    callers that haven't been migrated yet.
    """
    if servers is None:
        servers = [
            {
                "name": mcp_server_name or "mcp",
                "url": mcp_url,
                "transport": mcp_transport,
                "command": mcp_command or ["mcp_serve.sh"],
            }
        ]
    mcp_servers: dict[str, object] = {}
    for s in servers:
        mcp_servers[s["name"]] = _claude_mcp_entry(
            s.get("url"), s.get("transport", "http"), s.get("command")
        )
    result = {"mcpServers": mcp_servers}
    ClaudeMcpConfig.model_validate(result)
    return result
