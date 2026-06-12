"""Canonical ↔ backend-native tool name translation.

This module owns the translation table per ``APP_DOMAINS §7``. It is a
taxonomy module and must not import from any domain (especially Engines)
so that render/engines initialization stays cycle-free.
"""

from __future__ import annotations

# Mapping of backend name -> canonical capability name -> native tool name.
# This is the single source of truth for tool-name translation; both
# ``core.engines.render`` and the backend adapters read it from here.
NATIVE_TOOL_NAMES: dict[str, dict[str, str]] = {
    "claude_code": {
        "fs.read": "Read",
        "fs.write": "Write",
        "fs.edit": "Edit",
        "fs.multi_edit": "MultiEdit",
        "fs.list": "LS",
        "fs.glob": "Glob",
        "fs.grep": "Grep",
        "shell.exec": "Bash",
        "http.fetch": "WebFetch",
        "web.search": "WebSearch",
        "notebook.edit": "NotebookEdit",
        "interaction.ask_user": "AskUserQuestion",
        "agent.task": "Task",
    },
    "opencode": {
        "fs.read": "read_file",
        "fs.write": "write_file",
        "fs.list": "list_directory",
        "fs.glob": "glob",
        "fs.grep": "grep",
        "shell.exec": "run_command",
        "http.fetch": "web_fetch",
        "interaction.ask_user": "question",
        "agent.task": "task",
        "todo.read": "todoread",
        "todo.write": "todowrite",
    },
}


class UnknownToolError(KeyError):
    """Raised when a canonical tool or backend is not in the taxonomy."""


def _mapping_for(backend: str) -> dict[str, str]:
    """Return the canonical→native mapping for *backend*.

    Raises :class:`UnknownToolError` when the backend is not known.
    """
    mapping = NATIVE_TOOL_NAMES.get(backend)
    if mapping is None:
        raise UnknownToolError(f"Unknown backend {backend!r}")
    return mapping


def to_native(capability: str, backend: str) -> str:
    """Translate a canonical capability name to a backend-native tool name.

    Raises :class:`UnknownToolError` if the capability or backend mapping
    is not in the taxonomy.
    """
    mapping = _mapping_for(backend)
    native = mapping.get(capability)
    if native is None:
        raise UnknownToolError(
            f"No {backend!r} mapping for canonical tool {capability!r}"
        )
    return native


def from_native(native: str, backend: str) -> str:
    """Translate a backend-native tool name back to its canonical name.

    Raises :class:`UnknownToolError` if the native name / backend pair
    is not in the taxonomy.
    """
    mapping = _mapping_for(backend)
    for canonical, nn in mapping.items():
        if nn == native:
            return canonical
    raise UnknownToolError(f"Unknown {backend!r} native tool {native!r}")


def native_tool_names(backend: str) -> frozenset[str]:
    """Return every native tool name registered for *backend*."""
    return frozenset(_mapping_for(backend).values())


def backend_tool_name(canonical_name: str, backend: str) -> str | None:
    """Return the backend-specific tool name for a canonical tool.

    Returns ``None`` when the backend is unknown or has no mapping for the
    tool. This is the lenient lookup used by callers that need to degrade
    gracefully.
    """
    mapping = NATIVE_TOOL_NAMES.get(backend)
    if mapping is None:
        return None
    return mapping.get(canonical_name)


def canonicalize(name: str) -> str | None:
    """Return the canonical name for *name* if it is known to any backend.

    *name* may already be canonical (a key in any backend's mapping) or it
    may be a backend-native name. If it matches neither, return ``None``.
    """
    for backend_mapping in NATIVE_TOOL_NAMES.values():
        if name in backend_mapping:
            return name
        for canonical, native in backend_mapping.items():
            if native == name:
                return canonical
    return None


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
    target_backend: str,
    *,
    mcp_prefixes: dict[str, str] | None = None,
) -> str:
    """Translate any tool name into *target_backend*'s native vocabulary.

    Resolution order:

    1. Already canonical or native to some backend → ``to_native``.
    2. MCP-prefixed (``mcp_prefixes`` maps source→target prefix) → rewrite
       the prefix.
    3. Unknown → passthrough unchanged.

    Gap coverage: when step 1 yields a canonical tool with no native
    mapping in *target_backend*, the env-MCP name
    ``<target_prefix><canonical>`` is returned instead of dropping the
    tool. The target prefix is taken from *mcp_prefixes*; if no prefixes
    are supplied the original name is passed through.
    """
    canonical = canonicalize(name)
    if canonical is not None:
        mapping = NATIVE_TOOL_NAMES.get(target_backend)
        if mapping is not None and canonical in mapping:
            return mapping[canonical]
        # Gap coverage: expose the canonical capability through the env-MCP.
        target_prefix = _target_mcp_prefix(mcp_prefixes)
        if target_prefix is not None:
            return f"{target_prefix}{canonical}"
        # ponytail: no target prefix supplied, cannot construct env-MCP name
        return name

    if mcp_prefixes:
        for source_prefix, target_prefix in mcp_prefixes.items():
            if name.startswith(source_prefix):
                return f"{target_prefix}{name[len(source_prefix):]}"

    return name
