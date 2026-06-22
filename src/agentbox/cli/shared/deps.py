"""CLI-layer shared singletons — mirrors ``api/deps.py`` factories.

CLI commands should NOT import from ``agentbox.api.deps`` per the
dependency-direction rule (CLI → API is a reverse dependency). Instead
they use these CLI-owned factory functions, which are functionally
identical to, but architecturally independent from, the API layer.

Each factory is ``@lru_cache`` so a typer callback context or scoped
command group can call it without recreating heavy objects.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

import typer
from rich.console import Console
from rich.text import Text

from agentbox.core.config import Settings, load_settings
from agentbox.core.constants import EventType
from agentbox.core.db import Database
from agentbox.core.service import SessionStore
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.workspaces.mcp.client import McpRegistry


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    return SessionStore(get_settings().db_path)


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database(get_settings().db_path)


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_store(), get_settings(), get_mcp_registry(), db=get_db())


# ---------------------------------------------------------------------------
# Shared console + presentation helpers
#
# These live here (the CLI dependency base) so every command group imports a
# single surface: ``from agentbox.cli.shared import console, get_store, ...``.
# ``common.py`` re-exports them for backwards compatibility.
# ---------------------------------------------------------------------------

console = Console()

# Error codes: 1 = not found / expected failure, 2 = invalid input, 3 = upstream


@contextmanager
def handle_cli_errors() -> Iterator[None]:
    """Map known service errors to coloured ``typer.Exit``.

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
