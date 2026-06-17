"""Pi native tool-name mapping.

CanonicalTool → pi native name (v0.75.4).
Built-in tools (on by default): read/bash/edit/write.
Additional tools (off by default, enable with --tools): grep/find/ls.
"""

from __future__ import annotations

from agentbox.core.tools.canonical import CanonicalTool

NATIVE_TOOLS: dict[CanonicalTool, str] = {
    CanonicalTool.FS_READ: "read",
    CanonicalTool.SHELL_EXEC: "bash",
    CanonicalTool.FS_EDIT: "edit",
    CanonicalTool.FS_WRITE: "write",
    CanonicalTool.FS_GREP: "grep",
    CanonicalTool.FS_GLOB: "find",
    CanonicalTool.FS_LIST: "ls",
}
