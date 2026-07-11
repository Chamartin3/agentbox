"""OpenCode native tool-name mapping.

CanonicalTool → OpenCode snake_case native name.
"""

from __future__ import annotations

from agentbox.core.data import CanonicalTool

NATIVE_TOOLS: dict[CanonicalTool, str] = {
    CanonicalTool.FS_READ: "read_file",
    CanonicalTool.FS_WRITE: "write_file",
    CanonicalTool.FS_LIST: "list_directory",
    CanonicalTool.FS_GLOB: "glob",
    CanonicalTool.FS_GREP: "grep",
    CanonicalTool.SHELL_EXEC: "run_command",
    CanonicalTool.HTTP_FETCH: "web_fetch",
    CanonicalTool.INTERACTION_ASK_USER: "question",
    CanonicalTool.AGENT_TASK: "task",
    CanonicalTool.TODO_READ: "todoread",
    CanonicalTool.TODO_WRITE: "todowrite",
}
