from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.workspace.mcp.client.tool_manifest import Tool

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
