"""CLI-scoped constants: rich styles and CLI-only magic values.

Domain value-sets (session modes, backends, event types, workspace
sentinels, …) live in :mod:`agentbox.core.constants` and are reused —
not redefined — here. This module only owns values that are specific to
the terminal presentation layer or to CLI-originated DB writes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from agentbox.core.constants import EventType

# ---------------------------------------------------------------------------
# Canonical recursive JSON value alias.
# Covers every value that json.dumps / json.loads can produce.
# ---------------------------------------------------------------------------

type JsonValue = str | int | float | bool | None | dict[str, JsonValue] | list[JsonValue]

# Sentinel value accepted by workspace resolution to request a fresh tmp dir.
EPHEMERAL_WORKSPACE: Final[str] = "<ephemeral>"

__all__ = [
    "JsonValue",
    "Style",
    "NA",
    "CLI_AUTHOR",
    "CLI_SOURCE",
    "RUNNER_CLEAR",
    "EVENT_STYLES",
    "EPHEMERAL_WORKSPACE",
]


class Style(StrEnum):
    """Rich markup style names used across CLI output.

    Use these instead of literal ``[red]…[/red]`` markup so colour choices
    have a single source of truth. Prefer the ``Renderer`` message helpers
    (``render.error`` etc.) over hand-writing markup with these.
    """

    SUCCESS = "green"
    ERROR = "red"
    WARN = "yellow"
    INFO = "cyan"
    DIM = "dim"
    ACCENT = "blue"
    HEADER = "bold cyan"


# Placeholder shown for absent / empty values in tables and detail panels.
NA: Final[str] = "—"  # em dash

# Provenance recorded on DB writes that originate from the CLI.
CLI_AUTHOR: Final[str] = "cli"
CLI_SOURCE: Final[str] = "cli"

# Sentinel accepted by ``agent def edit --runner clear`` to unbind a profile.
RUNNER_CLEAR: Final[str] = "clear"

# Event-type → rich style, the single lookup used by streaming/log renderers.
EVENT_STYLES: Final[dict[str, str]] = {
    EventType.TEXT: "white",
    EventType.LOG: "dim",
    EventType.TOOL_CALL: "cyan",
    EventType.TOOL_RESULT: "green",
    EventType.USAGE: "yellow",
    EventType.RETRY: "bright_yellow",
    EventType.THINKING: "bright_blue",
    EventType.TIMEOUT: "bright_red",
    EventType.DONE: "bold",
    "error": "red",
    "warning": "yellow",
}
