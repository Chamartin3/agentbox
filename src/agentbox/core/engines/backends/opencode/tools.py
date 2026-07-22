"""OpenCode native tool ids and CanonicalTool mapping.

``OpenCodeTool`` is the single source of truth for the built-in tool ids
opencode registers; ``NATIVE_TOOLS`` maps our canonical vocabulary onto it.
"""

from __future__ import annotations

from enum import StrEnum

from agentbox.core.data import CanonicalTool


class OpenCodeTool(StrEnum):
    """Built-in tool ids as opencode registers them (``opencode debug agent build``)."""

    INVALID = "invalid"
    QUESTION = "question"
    BASH = "bash"
    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    LIST = "list"
    GLOB = "glob"
    GREP = "grep"
    WEBFETCH = "webfetch"
    TASK = "task"
    TODOWRITE = "todowrite"
    TODOREAD = "todoread"
    SKILL = "skill"


NATIVE_TOOLS: dict[CanonicalTool, OpenCodeTool] = {
    CanonicalTool.FS_READ: OpenCodeTool.READ,
    CanonicalTool.FS_WRITE: OpenCodeTool.WRITE,
    CanonicalTool.FS_LIST: OpenCodeTool.LIST,
    CanonicalTool.FS_GLOB: OpenCodeTool.GLOB,
    CanonicalTool.FS_GREP: OpenCodeTool.GREP,
    CanonicalTool.SHELL_EXEC: OpenCodeTool.BASH,
    CanonicalTool.HTTP_FETCH: OpenCodeTool.WEBFETCH,
    CanonicalTool.INTERACTION_ASK_USER: OpenCodeTool.QUESTION,
    CanonicalTool.AGENT_TASK: OpenCodeTool.TASK,
    CanonicalTool.TODO_READ: OpenCodeTool.TODOREAD,
    CanonicalTool.TODO_WRITE: OpenCodeTool.TODOWRITE,
}

# Built-ins gated behind the agent allow-list. opencode auto-injects all of
# these under --dangerously-skip-permissions, so each must be named to disable
# it. ``SKILL`` is the MCP/skill bridge and is governed separately (kept on).
# ponytail: the enum is hardcoded from opencode 1.17.x; test_opencode_builtins
# re-checks it against a live opencode so an upgrade that adds a builtin fails
# loudly instead of silently leaking a tool.
NATIVE_BUILTINS: frozenset[OpenCodeTool] = frozenset(OpenCodeTool) - {OpenCodeTool.SKILL}
