"""Codex native tool-name mapping.

Codex is a Claude Code API-compatible replacement; its native
tool names mirror Claude Code's PascalCase convention.
"""

from __future__ import annotations

from agentbox.core.data import CanonicalTool

NATIVE_TOOLS: dict[CanonicalTool, str] = {
    CanonicalTool.FS_READ: "Read",
    CanonicalTool.FS_WRITE: "Write",
    CanonicalTool.FS_EDIT: "Edit",
    CanonicalTool.FS_MULTI_EDIT: "MultiEdit",
    CanonicalTool.FS_LIST: "LS",
    CanonicalTool.FS_GLOB: "Glob",
    CanonicalTool.FS_GREP: "Grep",
    CanonicalTool.SHELL_EXEC: "Bash",
    CanonicalTool.HTTP_FETCH: "WebFetch",
    CanonicalTool.WEB_SEARCH: "WebSearch",
    CanonicalTool.NOTEBOOK_EDIT: "NotebookEdit",
    CanonicalTool.INTERACTION_ASK_USER: "AskUserQuestion",
    CanonicalTool.AGENT_TASK: "Task",
}
