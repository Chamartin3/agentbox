"""Curated capability registry — canonical taxonomy for all host-env tools.

Each entry declares a capability the host-env MCP server exposes plus the
JSON-schema-ish shape of its grant params. This module is the single source
of truth the API, grant resolver, and MCP implementations agree on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentbox.core.tools.canonical import CanonicalTool


@dataclass(frozen=True)
class Capability:
    name: CanonicalTool
    description: str
    grant_schema: dict[str, Any]
    default_granted: bool = False


CAPABILITIES: dict[CanonicalTool, Capability] = {
    CanonicalTool.FS_READ: Capability(
        name=CanonicalTool.FS_READ,
        description="Read a file under one of the allowed paths.",
        grant_schema={
            "allowed_paths": {"type": "list[str]", "required": True},
            "max_bytes": {"type": "int", "default": 1_048_576},
        },
    ),
    CanonicalTool.FS_LIST: Capability(
        name=CanonicalTool.FS_LIST,
        description="List entries under one of the allowed paths.",
        grant_schema={
            "allowed_paths": {"type": "list[str]", "required": True},
        },
    ),
    CanonicalTool.FS_WRITE: Capability(
        name=CanonicalTool.FS_WRITE,
        description="Write a file under one of the allowed paths (off by default).",
        grant_schema={
            "allowed_paths": {"type": "list[str]", "required": True},
            "max_bytes": {"type": "int", "default": 1_048_576},
        },
    ),
    CanonicalTool.SHELL_EXEC: Capability(
        name=CanonicalTool.SHELL_EXEC,
        description="Run a shell command matching the allowlist regex.",
        grant_schema={
            "command_allowlist": {"type": "list[str]", "required": True},
            "timeout_seconds": {"type": "int", "default": 30},
            "cwd": {"type": "str"},
        },
    ),
    CanonicalTool.GIT_STATUS: Capability(
        name=CanonicalTool.GIT_STATUS,
        description="git status on a repo under allowed_paths.",
        grant_schema={"allowed_paths": {"type": "list[str]", "required": True}},
    ),
    CanonicalTool.GIT_LOG: Capability(
        name=CanonicalTool.GIT_LOG,
        description="git log on a repo under allowed_paths.",
        grant_schema={"allowed_paths": {"type": "list[str]", "required": True}},
    ),
    CanonicalTool.GIT_DIFF: Capability(
        name=CanonicalTool.GIT_DIFF,
        description="git diff on a repo under allowed_paths.",
        grant_schema={"allowed_paths": {"type": "list[str]", "required": True}},
    ),
    CanonicalTool.HTTP_FETCH: Capability(
        name=CanonicalTool.HTTP_FETCH,
        description="HTTP fetch against an allowlisted host.",
        grant_schema={
            "host_allowlist": {"type": "list[str]", "required": True},
            "methods": {"type": "list[str]", "default": ["GET"]},
        },
    ),
    CanonicalTool.ENV_GET: Capability(
        name=CanonicalTool.ENV_GET,
        description="Read allowlisted environment variable.",
        grant_schema={"allowlist": {"type": "list[str]", "required": True}},
    ),
    CanonicalTool.AGENTBOX_WORKSPACE_INFO: Capability(
        name=CanonicalTool.AGENTBOX_WORKSPACE_INFO,
        description="Read-only metadata about the current workspace.",
        grant_schema={},
        default_granted=True,
    ),
}
