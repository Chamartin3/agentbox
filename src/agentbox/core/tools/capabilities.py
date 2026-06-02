"""Curated capability registry — canonical taxonomy for all host-env tools.

Each entry declares a capability the host-env MCP server exposes plus the
JSON-schema-ish shape of its grant params. This module is the single source
of truth the API, grant resolver, and MCP implementations agree on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    grant_schema: dict[str, Any]
    default_granted: bool = False


CAPABILITIES: dict[str, Capability] = {
    "fs.read": Capability(
        name="fs.read",
        description="Read a file under one of the allowed paths.",
        grant_schema={
            "allowed_paths": {"type": "list[str]", "required": True},
            "max_bytes": {"type": "int", "default": 1_048_576},
        },
    ),
    "fs.list": Capability(
        name="fs.list",
        description="List entries under one of the allowed paths.",
        grant_schema={
            "allowed_paths": {"type": "list[str]", "required": True},
        },
    ),
    "fs.write": Capability(
        name="fs.write",
        description="Write a file under one of the allowed paths (off by default).",
        grant_schema={
            "allowed_paths": {"type": "list[str]", "required": True},
            "max_bytes": {"type": "int", "default": 1_048_576},
        },
    ),
    "shell.exec": Capability(
        name="shell.exec",
        description="Run a shell command matching the allowlist regex.",
        grant_schema={
            "command_allowlist": {"type": "list[str]", "required": True},
            "timeout_seconds": {"type": "int", "default": 30},
            "cwd": {"type": "str"},
        },
    ),
    "git.status": Capability(
        name="git.status",
        description="git status on a repo under allowed_paths.",
        grant_schema={"allowed_paths": {"type": "list[str]", "required": True}},
    ),
    "git.log": Capability(
        name="git.log",
        description="git log on a repo under allowed_paths.",
        grant_schema={"allowed_paths": {"type": "list[str]", "required": True}},
    ),
    "git.diff": Capability(
        name="git.diff",
        description="git diff on a repo under allowed_paths.",
        grant_schema={"allowed_paths": {"type": "list[str]", "required": True}},
    ),
    "http.fetch": Capability(
        name="http.fetch",
        description="HTTP fetch against an allowlisted host.",
        grant_schema={
            "host_allowlist": {"type": "list[str]", "required": True},
            "methods": {"type": "list[str]", "default": ["GET"]},
        },
    ),
    "env.get": Capability(
        name="env.get",
        description="Read allowlisted environment variable.",
        grant_schema={"allowlist": {"type": "list[str]", "required": True}},
    ),
    "agentbox.workspace_info": Capability(
        name="agentbox.workspace_info",
        description="Read-only metadata about the current workspace.",
        grant_schema={},
        default_granted=True,
    ),
}
