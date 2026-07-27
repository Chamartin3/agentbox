"""MCP vocabulary — the ``Tool`` shape, prefix-grouping, and the per-server
``McpToolManifest`` (group expansion + reference resolution).

Merges the former client/types.py + client/grouping.py + client/tool_manifest.py.
"""

from __future__ import annotations

from agentbox.core.data import JsonSchemaDict

from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str = ""
    input_schema: JsonSchemaDict | None = None


_READ_PREFIXES = ("get_", "list_", "search_", "check_", "select_", "find_")


def _derive_prefix(name: str) -> str:
    parts = name.split("_", 1)
    return parts[0]


def _has_read_prefix(name: str) -> bool:
    if any(name.startswith(p) for p in _READ_PREFIXES):
        return True
    base = name.rstrip("_")
    return base in {"get", "list", "search", "check", "select", "find"}


def derive_groups(server_name: str, tools: list[Tool]) -> dict[str, list[str]]:
    """Apply prefix-grouping rules and return ``{group_key: [tool_names]}``."""
    groups: dict[str, list[str]] = {}
    prefix_map: dict[str, list[str]] = {}

    for t in tools:
        prefix = _derive_prefix(t.name)
        prefix_map.setdefault(prefix, []).append(t.name)

    for prefix, names in prefix_map.items():
        read_tools: list[str] = []
        write_tools: list[str] = []
        for n in names:
            suffix = n[len(prefix) :]
            stripped = suffix.lstrip("_")
            if _has_read_prefix(stripped):
                read_tools.append(n)
            else:
                write_tools.append(n)

        if read_tools:
            group_key = f"{server_name}.{prefix}.read"
            groups[group_key] = read_tools
        if write_tools:
            group_key = f"{server_name}.{prefix}.write"
            groups[group_key] = write_tools

        all_key = f"{server_name}.{prefix}"
        groups[all_key] = names

    return groups


def resolve_group_ref(ref: str, groups: dict[str, list[str]]) -> list[str]:
    """Resolve a reference string to a list of tool names.

    Reference syntax:
    - ``@server:group`` — explicit server.
    - ``mcp:server/tool`` — fully qualified single tool.
    - ``@group`` — implicit; unambiguous across servers.
    """
    if ref.startswith("mcp:"):
        tool = ref[4:]
        server, _, tool_name = tool.partition("/")
        return [tool_name]

    if not ref.startswith("@"):
        raise ValueError(f"not a group reference: {ref!r}")

    inner = ref[1:]

    if ":" in inner:
        server, _, group_name = inner.partition(":")
        key = f"{server}.{group_name}"
        direct = groups.get(key)
        if direct is not None:
            return direct
        read_key = f"{server}.{group_name}.read"
        if read_key in groups:
            return groups[read_key]
        write_key = f"{server}.{group_name}.write"
        if write_key in groups:
            return groups[write_key]
        raise ValueError(f"unknown group: {ref}")

    matches: list[str] = []
    for key, tool_names in groups.items():
        _, _, suffix = key.partition(".")
        if suffix == inner or suffix.startswith(f"{inner}."):
            matches.extend(tool_names)

    if not matches:
        raise ValueError(f"unknown group: {ref}")

    return matches


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
