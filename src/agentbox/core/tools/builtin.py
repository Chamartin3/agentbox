"""Canonical built-in tools taxonomy (Plan 08 Phase 10).

Defines the standardized tool names, signatures, and capability
alignment. Per-backend native names live in ``core.tools.translation``;
this module re-exports the lookup helpers for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentbox.core.tools.translation import (
    UnknownToolError,
    backend_tool_name,
    from_native,
    native_tool_names,
    to_native,
)


@dataclass(frozen=True)
class BuiltinToolSpec:
    """Canonical spec for one built-in tool.

    Attributes:
        name:          Canonical tool name (matches host_env capability key).
        description:   Human-readable description of what the tool does.
        capability:    Corresponding host_env capability (None for always-on).
        params:        Canonical parameter names (documentation only).
    """

    name: str
    description: str
    capability: str | None
    params: list[str] = field(default_factory=list)


# ── File system ──────────────────────────────────────────────────────────────

BUILTIN_TOOLS: tuple[BuiltinToolSpec, ...] = (
    BuiltinToolSpec(
        name="fs.read",
        description="Read file contents from the local filesystem.",
        capability="fs.read",
        params=["path"],
    ),
    BuiltinToolSpec(
        name="fs.write",
        description="Write or overwrite a file on the local filesystem.",
        capability="fs.write",
        params=["path", "content"],
    ),
    BuiltinToolSpec(
        name="fs.edit",
        description="Perform exact string replacements in a file.",
        capability=None,
        params=["file_path", "old_string", "new_string"],
    ),
    BuiltinToolSpec(
        name="fs.multi_edit",
        description="Perform multiple string replacements across files.",
        capability=None,
        params=[],
    ),
    BuiltinToolSpec(
        name="fs.list",
        description="List directory contents.",
        capability="fs.list",
        params=["path"],
    ),
    BuiltinToolSpec(
        name="fs.glob",
        description="Find files by glob patterns.",
        capability=None,
        params=["pattern"],
    ),
    BuiltinToolSpec(
        name="fs.grep",
        description="Search file contents with regex.",
        capability=None,
        params=["pattern"],
    ),

    # ── Shell ────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="shell.exec",
        description="Execute a shell command.",
        capability="shell.exec",
        params=["cmd", "cwd", "timeout"],
    ),

    # ── HTTP / Web ───────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="http.fetch",
        description="Fetch a URL over HTTP/HTTPS.",
        capability="http.fetch",
        params=["url", "method"],
    ),
    BuiltinToolSpec(
        name="web.search",
        description="Search the web.",
        capability=None,
        params=["query"],
    ),

    # ── Git ──────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="git.status",
        description="Show the working tree status.",
        capability="git.status",
        params=["repo_path"],
    ),

    # ── Environment ──────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="env.get",
        description="Read an environment variable.",
        capability="env.get",
        params=["name"],
    ),

    # ── Notebook ─────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="notebook.edit",
        description="Edit a Jupyter notebook cell.",
        capability=None,
        params=[],
    ),

    # ── Interaction ──────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="interaction.ask_user",
        description="Ask the user a question during execution.",
        capability=None,
        params=["question"],
    ),

    # ── Agent / Task ─────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="agent.task",
        description="Delegate work to a sub-agent.",
        capability=None,
        params=[],
    ),

    # ── Todo ─────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="todo.read",
        description="Read the current todo list.",
        capability=None,
        params=[],
    ),
    BuiltinToolSpec(
        name="todo.write",
        description="Create or update the todo list.",
        capability=None,
        params=[],
    ),

    # ── Agentbox ─────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name="agentbox.workspace_info",
        description="Return workspace metadata (always granted).",
        capability="agentbox.workspace_info",
        params=[],
    ),
)

# ── Lookup helpers ───────────────────────────────────────────────────────────

_TOOL_BY_NAME: dict[str, BuiltinToolSpec] = {t.name: t for t in BUILTIN_TOOLS}


def get_builtin(name: str) -> BuiltinToolSpec | None:
    """Return the spec for a canonical tool name, or None if unknown."""
    return _TOOL_BY_NAME.get(name)


__all__ = [
    "BUILTIN_TOOLS",
    "BuiltinToolSpec",
    "UnknownToolError",
    "backend_tool_name",
    "from_native",
    "get_builtin",
    "native_tool_names",
    "to_native",
]
