from __future__ import annotations

import typer
from rich.console import Console
from rich.text import Text

from agentbox.api.deps import get_loader

console = Console()

EVENT_STYLES: dict[str, str] = {
    "text": "white",
    "log": "dim",
    "tool_call": "cyan",
    "tool_result": "green",
    "usage": "yellow",
    "guardrail": "magenta",
    "done": "bold",
    "error": "red",
    "warning": "yellow",
}


def resolve_agent(agent_id: str):
    a = get_loader().get(agent_id)
    if a is None:
        console.print(f"[red]unknown agent[/red] {agent_id!r}")
        raise typer.Exit(2)
    return a


def checkmark(b: bool) -> Text:
    return Text("✓", style="green") if b else Text("·", style="dim")


def event_color(event_type: str) -> str:
    return EVENT_STYLES.get(event_type, "white")
