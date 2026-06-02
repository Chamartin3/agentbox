"""Canonical built-in tools taxonomy (Plan 08 Phase 10).

Defines the standardized tool names, signatures, and backend mappings
that align with the host_env capability set. Every backend built-in
tool has a canonical name here — config generation and tool-disabling
derive their per-backend names from this single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class UnknownToolError(KeyError):
    """Raised when a canonical tool or backend is not in the taxonomy."""


@dataclass(frozen=True)
class BuiltinToolSpec:
    """Canonical spec for one built-in tool.

    Attributes:
        name:          Canonical tool name (matches host_env capability key).
        description:   Human-readable description of what the tool does.
        capability:    Corresponding host_env capability (None for always-on).
        backend_names: Per-backend native tool names for config generation.
                       Keys are runner kinds; value is the backend's own name
                       for this tool (used in agents.json / opencode.json).
        params:        Canonical parameter names (documentation only).
    """

    name: str
    description: str
    capability: str | None
    backend_names: dict[str, str] = field(default_factory=dict)
    params: list[str] = field(default_factory=list)


# ── File system ──────────────────────────────────────────────────────────────

BUILTIN_TOOLS: tuple[BuiltinToolSpec, ...] = (
    BuiltinToolSpec(
        name="fs.read",
        description="Read file contents from the local filesystem.",
        capability="fs.read",
        backend_names={"claude_code": "Read", "opencode": "read_file"},
        params=["path"],
    ),
    BuiltinToolSpec(
        name="fs.write",
        description="Write or overwrite a file on the local filesystem.",
        capability="fs.write",
        backend_names={"claude_code": "Write", "opencode": "write_file"},
        params=["path", "content"],
    ),
    BuiltinToolSpec(
        name="fs.edit",
        description="Perform exact string replacements in a file.",
        capability=None,
        backend_names={"claude_code": "Edit"},
        params=["file_path", "old_string", "new_string"],
    ),
    BuiltinToolSpec(
        name="fs.multi_edit",
        description="Perform multiple string replacements across files.",
        capability=None,
        backend_names={"claude_code": "MultiEdit"},
        params=[],
    ),
    BuiltinToolSpec(
        name="fs.list",
        description="List directory contents.",
        capability="fs.list",
        backend_names={"claude_code": "LS", "opencode": "list_directory"},
        params=["path"],
    ),
    BuiltinToolSpec(
        name="fs.glob",
        description="Find files by glob patterns.",
        capability=None,
        backend_names={"claude_code": "Glob", "opencode": "glob"},
        params=["pattern"],
    ),
    BuiltinToolSpec(
        name="fs.grep",
        description="Search file contents with regex.",
        capability=None,
        backend_names={"claude_code": "Grep", "opencode": "grep"},
        params=["pattern"],
    ),

    # ── Shell ────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="shell.exec",
        description="Execute a shell command.",
        capability="shell.exec",
        backend_names={"claude_code": "Bash", "opencode": "run_command"},
        params=["cmd", "cwd", "timeout"],
    ),

    # ── HTTP / Web ───────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="http.fetch",
        description="Fetch a URL over HTTP/HTTPS.",
        capability="http.fetch",
        backend_names={"claude_code": "WebFetch", "opencode": "web_fetch"},
        params=["url", "method"],
    ),
    BuiltinToolSpec(
        name="web.search",
        description="Search the web.",
        capability=None,
        backend_names={"claude_code": "WebSearch"},
        params=["query"],
    ),

    # ── Git ──────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="git.status",
        description="Show the working tree status.",
        capability="git.status",
        backend_names={},
        params=["repo_path"],
    ),

    # ── Environment ──────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="env.get",
        description="Read an environment variable.",
        capability="env.get",
        backend_names={},
        params=["name"],
    ),

    # ── Notebook ─────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="notebook.edit",
        description="Edit a Jupyter notebook cell.",
        capability=None,
        backend_names={"claude_code": "NotebookEdit"},
        params=[],
    ),

    # ── Interaction ──────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="interaction.ask_user",
        description="Ask the user a question during execution.",
        capability=None,
        backend_names={"claude_code": "AskUserQuestion", "opencode": "question"},
        params=["question"],
    ),

    # ── Agent / Task ─────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="agent.task",
        description="Delegate work to a sub-agent.",
        capability=None,
        backend_names={"claude_code": "Task", "opencode": "task"},
        params=[],
    ),

    # ── Todo ─────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="todo.read",
        description="Read the current todo list.",
        capability=None,
        backend_names={"opencode": "todoread"},
        params=[],
    ),
    BuiltinToolSpec(
        name="todo.write",
        description="Create or update the todo list.",
        capability=None,
        backend_names={"opencode": "todowrite"},
        params=[],
    ),

    # ── Agentbox ─────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="agentbox.workspace_info",
        description="Return workspace metadata (always granted).",
        capability="agentbox.workspace_info",
        backend_names={},
        params=[],
    ),
)

# ── Lookup helpers ───────────────────────────────────────────────────────────

_TOOL_BY_NAME: dict[str, BuiltinToolSpec] = {t.name: t for t in BUILTIN_TOOLS}

# Reverse index: (native_name, backend) → canonical name
_NATIVE_TO_CANONICAL: dict[tuple[str, str], str] = {}
for _t in BUILTIN_TOOLS:
    for _bk, _nn in _t.backend_names.items():
        _NATIVE_TO_CANONICAL[(_nn, _bk)] = _t.name


def get_builtin(name: str) -> BuiltinToolSpec | None:
    """Return the spec for a canonical tool name, or None if unknown."""
    return _TOOL_BY_NAME.get(name)


def backend_tool_name(canonical_name: str, runner_kind: str) -> str | None:
    """Return the backend-specific tool name for a canonical tool.

    Returns None when the backend has no mapping for this tool.
    """
    spec = get_builtin(canonical_name)
    if spec is None:
        return None
    return spec.backend_names.get(runner_kind)


# ── Translation (total — raise on unknown) ───────────────────────────────────

def to_native(capability: str, backend: str) -> str:
    """Translate a canonical capability name to a backend-native tool name.

    Raises :class:`UnknownToolError` if the capability or backend mapping
    is not in the taxonomy.
    """
    spec = _TOOL_BY_NAME.get(capability)
    if spec is None:
        raise UnknownToolError(
            f"Unknown canonical tool {capability!r}"
        )
    native = spec.backend_names.get(backend)
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
    key = (native, backend)
    canonical = _NATIVE_TO_CANONICAL.get(key)
    if canonical is None:
        raise UnknownToolError(
            f"Unknown {backend!r} native tool {native!r}"
        )
    return canonical


def native_tool_names(backend: str) -> frozenset[str]:
    """Return every native tool name registered for *backend*."""
    return frozenset(
        nn for t in BUILTIN_TOOLS for bk, nn in t.backend_names.items() if bk == backend
    )
