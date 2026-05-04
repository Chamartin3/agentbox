"""Built-in tool registry (Plan 08 Phase 10).

Canonical taxonomy: each BuiltinToolSpec maps a tool name + signature to
the host_env capability it corresponds to, plus per-backend native names
for config-generation.

The canonical names match the host_env capability keys so operators can
reason about grants and tool disables with the same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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


BUILTIN_TOOLS: tuple[BuiltinToolSpec, ...] = (
    BuiltinToolSpec(
        name="fs.read",
        description="Read file contents from the local filesystem.",
        capability="fs.read",
        backend_names={
            "claude_code": "Read",
            "opencode": "read_file",
        },
        params=["path"],
    ),
    BuiltinToolSpec(
        name="fs.write",
        description="Write or overwrite a file on the local filesystem.",
        capability="fs.write",
        backend_names={
            "claude_code": "Write",
            "opencode": "write_file",
        },
        params=["path", "content"],
    ),
    BuiltinToolSpec(
        name="fs.list",
        description="List directory contents.",
        capability="fs.list",
        backend_names={
            "claude_code": "LS",
            "opencode": "list_directory",
        },
        params=["path"],
    ),
    BuiltinToolSpec(
        name="shell.exec",
        description="Execute a shell command.",
        capability="shell.exec",
        backend_names={
            "claude_code": "Bash",
            "opencode": "run_command",
        },
        params=["cmd", "cwd", "timeout"],
    ),
    BuiltinToolSpec(
        name="http.fetch",
        description="Fetch a URL over HTTP/HTTPS.",
        capability="http.fetch",
        backend_names={
            "claude_code": "WebFetch",
            "opencode": "web_fetch",
        },
        params=["url", "method"],
    ),
    BuiltinToolSpec(
        name="web.search",
        description="Search the web.",
        capability=None,
        backend_names={
            "claude_code": "WebSearch",
        },
        params=["query"],
    ),
    BuiltinToolSpec(
        name="git.status",
        description="Show the working tree status.",
        capability="git.status",
        backend_names={},
        params=["repo_path"],
    ),
    BuiltinToolSpec(
        name="env.get",
        description="Read an environment variable.",
        capability="env.get",
        backend_names={},
        params=["name"],
    ),
    BuiltinToolSpec(
        name="agentbox.workspace_info",
        description="Return workspace metadata (always granted).",
        capability="agentbox.workspace_info",
        backend_names={},
        params=[],
    ),
)

_TOOL_BY_NAME: dict[str, BuiltinToolSpec] = {t.name: t for t in BUILTIN_TOOLS}


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
