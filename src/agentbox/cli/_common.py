from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import typer
from rich.console import Console
from rich.text import Text

from agentbox.cli._deps import get_store
from agentbox.core.constants import EventType

console = Console()

# ---------------------------------------------------------------------------
# Service error → typer.Exit mapping
# ---------------------------------------------------------------------------

# Error codes: 1 = not found / expected failure, 2 = invalid input, 3 = upstream


@contextmanager
def handle_cli_errors() -> Iterator[None]:
    """Context manager that maps known service errors to coloured typer.Exit.

    Usage::

        with handle_cli_errors():
            result = some_service(store, ...)
            console.print(...)

    ``LookupError`` (NotFound) → exit 1, ``ValueError`` (AlreadyExists,
    Invalid) → exit 2, ``RuntimeError`` → exit 3.
    """
    try:
        yield
    except LookupError as exc:
        console.print(f"[red]not found:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ValueError as exc:
        console.print(f"[red]invalid:[/red] {exc}")
        raise typer.Exit(2) from exc
    except RuntimeError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(3) from exc

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
