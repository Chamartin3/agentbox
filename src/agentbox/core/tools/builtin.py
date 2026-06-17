"""Canonical built-in tools taxonomy (Plan 08 Phase 10).

Defines the standardized tool names, signatures, and capability
alignment. Per-backend native-name maps live in
``agentbox.core.engines.backends.<be>.tools``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentbox.core.tools.canonical import CanonicalTool


@dataclass(frozen=True)
class BuiltinToolSpec:
    """Canonical spec for one built-in tool.

    Attributes:
        name:          Canonical tool name (matches host_env capability key).
        description:   Human-readable description of what the tool does.
        capability:    Corresponding host_env capability (None for always-on).
        params:        Canonical parameter names (documentation only).
    """

    name: CanonicalTool
    description: str
    capability: CanonicalTool | None
    params: list[str] = field(default_factory=list)


# ── File system ──────────────────────────────────────────────────────────────

BUILTIN_TOOLS: tuple[BuiltinToolSpec, ...] = (
    BuiltinToolSpec(
        name=CanonicalTool.FS_READ,
        description="Read file contents from the local filesystem.",
        capability=CanonicalTool.FS_READ,
        params=["path"],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.FS_WRITE,
        description="Write or overwrite a file on the local filesystem.",
        capability=CanonicalTool.FS_WRITE,
        params=["path", "content"],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.FS_EDIT,
        description="Perform exact string replacements in a file.",
        capability=None,
        params=["file_path", "old_string", "new_string"],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.FS_MULTI_EDIT,
        description="Perform multiple string replacements across files.",
        capability=None,
        params=[],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.FS_LIST,
        description="List directory contents.",
        capability=CanonicalTool.FS_LIST,
        params=["path"],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.FS_GLOB,
        description="Find files by glob patterns.",
        capability=None,
        params=["pattern"],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.FS_GREP,
        description="Search file contents with regex.",
        capability=None,
        params=["pattern"],
    ),

    # ── Shell ────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.SHELL_EXEC,
        description="Execute a shell command.",
        capability=CanonicalTool.SHELL_EXEC,
        params=["cmd", "cwd", "timeout"],
    ),

    # ── HTTP / Web ───────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.HTTP_FETCH,
        description="Fetch a URL over HTTP/HTTPS.",
        capability=CanonicalTool.HTTP_FETCH,
        params=["url", "method"],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.WEB_SEARCH,
        description="Search the web.",
        capability=None,
        params=["query"],
    ),

    # ── Git ──────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.GIT_STATUS,
        description="Show the working tree status.",
        capability=CanonicalTool.GIT_STATUS,
        params=["repo_path"],
    ),

    # ── Environment ──────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.ENV_GET,
        description="Read an environment variable.",
        capability=CanonicalTool.ENV_GET,
        params=["name"],
    ),

    # ── Notebook ─────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.NOTEBOOK_EDIT,
        description="Edit a Jupyter notebook cell.",
        capability=None,
        params=[],
    ),

    # ── Interaction ──────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.INTERACTION_ASK_USER,
        description="Ask the user a question during execution.",
        capability=None,
        params=["question"],
    ),

    # ── Agent / Task ─────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.AGENT_TASK,
        description="Delegate work to a sub-agent.",
        capability=None,
        params=[],
    ),

    # ── Todo ─────────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.TODO_READ,
        description="Read the current todo list.",
        capability=None,
        params=[],
    ),
    BuiltinToolSpec(
        name=CanonicalTool.TODO_WRITE,
        description="Create or update the todo list.",
        capability=None,
        params=[],
    ),

    # ── Agentbox ─────────────────────────────────────────────────────────────

    BuiltinToolSpec(
        name=CanonicalTool.AGENTBOX_WORKSPACE_INFO,
        description="Return workspace metadata (always granted).",
        capability=CanonicalTool.AGENTBOX_WORKSPACE_INFO,
        params=[],
    ),
)

# ── Lookup helpers ───────────────────────────────────────────────────────────

_TOOL_BY_NAME: dict[CanonicalTool, BuiltinToolSpec] = {t.name: t for t in BUILTIN_TOOLS}


def get_builtin(name: str) -> BuiltinToolSpec | None:
    """Return the spec for a canonical tool name, or None if unknown."""
    try:
        tool = CanonicalTool(name)
    except ValueError:
        return None
    return _TOOL_BY_NAME.get(tool)


__all__ = [
    "BUILTIN_TOOLS",
    "BuiltinToolSpec",
    "get_builtin",
]
