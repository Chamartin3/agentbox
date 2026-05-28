from __future__ import annotations

import typer
from rich.console import Console
from rich.text import Text

from agentbox.cli._deps import get_store
from agentbox.core.constants import EventType

console = Console()

EVENT_STYLES: dict[str, str] = {
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


def resolve_agent(agent_id: str):
    a = get_store().get_agent_def(agent_id)
    if a is None:
        console.print(f"[red]unknown agent[/red] {agent_id!r}")
        raise typer.Exit(2)
    return a


def checkmark(b: bool) -> Text:
    return Text("✓", style="green") if b else Text("·", style="dim")


def event_color(event_type: str) -> str:
    return EVENT_STYLES.get(event_type, "white")
