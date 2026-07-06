from __future__ import annotations

from agentbox.core.workspaces.mcp.client.grouping import derive_groups
from agentbox.core.workspaces.mcp.client.types import Tool


class McpToolManifest:
    """Per-server tool manifest.

    Keyed by ``server_name -> list[Tool]``. Provides group expansion and
    reference resolution without touching the filesystem.
    """

    def __init__(self) -> None:
        self._servers: dict[str, list[Tool]] = {}
        self._groups: dict[str, list[str]] = {}
        self._tool_to_server: dict[str, str] = {}

    def set_servers(self, servers: dict[str, list[Tool]]) -> None:
        self._servers = {}
        self._groups = {}
        self._tool_to_server = {}
        for name, tools in servers.items():
            self._servers[name] = tools
            self._groups.update(derive_groups(name, tools))
            for t in tools:
                self._tool_to_server[t.name] = name

    @property
    def servers(self) -> dict[str, list[Tool]]:
        return dict(self._servers)

    @property
    def groups(self) -> dict[str, list[str]]:
        return dict(self._groups)

    def server_tools(self, server_name: str) -> list[Tool]:
        return list(self._servers.get(server_name, []))

    def resolve_group(self, ref: str) -> list[Tool]:
        if not ref.startswith("@"):
            raise ValueError(f"not a group reference: {ref!r}")

        inner = ref[1:]

        if ":" in inner:
            server, _, group_name = inner.partition(":")
            return self._tools_for_group(server, group_name)

        return self._resolve_implicit_group(inner)

    def resolve_tool(self, ref: str) -> Tool | None:
        if not ref.startswith("mcp:"):
            return None
        inner = ref[4:]
        server, _, tool_name = inner.partition("/")
        if not tool_name:
            return None
        for t in self._servers.get(server, []):
            if t.name == tool_name:
                return t
        return None

    def resolve_agent_tools(
        self, raw_tools: list[str], server_name: str | None = None
    ) -> list[str]:
        mcp_prefix = f"mcp__{server_name}__" if server_name else "mcp__"
        result: list[str] = []
        seen: set[str] = set()
        for tool in raw_tools:
            if tool.startswith("@"):
                expanded = self.resolve_group(tool)
                for t in expanded:
                    prefixed = f"{mcp_prefix}{t.name}"
                    if prefixed not in seen:
                        seen.add(prefixed)
                        result.append(prefixed)
            else:
                result.append(tool)
        return result

    def tool_count(self, server_name: str | None = None) -> int:
        if server_name is not None:
            return len(self._servers.get(server_name, []))
        return sum(len(tools) for tools in self._servers.values())

    def group_count(self) -> int:
        return len(self._groups)

    def _tools_for_group(self, server: str, group_name: str) -> list[Tool]:
        group_key = f"{server}.{group_name}"
        if group_key in self._groups:
            tool_names = self._groups[group_key]
        else:
            tool_names = self._groups.get(group_name, [])
        name_set = set(tool_names)
        return [t for t in self._servers.get(server, []) if t.name in name_set]

    def _resolve_implicit_group(self, group_name: str) -> list[Tool]:
        matches: list[tuple[str, list[str]]] = []
        for server in self._servers:
            key = f"{server}.{group_name}"
            if key in self._groups:
                matches.append((server, self._groups[key]))

        if len(matches) > 1:
            server_list = ", ".join(m[0] for m in matches)
            raise ValueError(
                f"ambiguous group '@{group_name}' matches servers: {server_list}. "
                f"Use '@server:{group_name}' to disambiguate."
            )
        if not matches:
            raise ValueError(f"unknown group: @{group_name}")
        name_set = set(matches[0][1])
        return [t for t in self._servers.get(matches[0][0], []) if t.name in name_set]
