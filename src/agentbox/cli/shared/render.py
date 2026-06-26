"""CLI rendering helpers — reusable output/formatting layer.

Every command accesses a shared ``Renderer`` via ``ctx.obj.render``.
Common output operations (success/error/warn/dim messages, tables, KV
panels) live here so command bodies can stop writing inline Rich markup
and magic strings. The single ``Console`` instance here is the module-
level singleton reused by all commands — no second console is created.
"""

from __future__ import annotations

from typing import Sequence

from rich.console import Console, RenderableType
from rich.json import JSON
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from agentbox.cli.shared.constants import EVENT_STYLES, NA, Style, JsonValue

# ---------------------------------------------------------------------------
# Module-level console singleton — the single Rich output stream for all CLI.
# Import as ``from agentbox.cli.shared import console`` via __init__.py.
# ---------------------------------------------------------------------------

console = Console()

# ---------------------------------------------------------------------------
# Back-compat module-level helpers (moved from deps.py; same bodies).
# ---------------------------------------------------------------------------


def checkmark(b: bool) -> Text:
    """Return a green checkmark for True, a dim dot for False."""
    return Text("✓", style="green") if b else Text("·", style="dim")


def event_color(event_type: str) -> str:
    """Resolve an ``EventType`` string to a Rich style."""
    return EVENT_STYLES.get(event_type, "white")


class Renderer:
    """Shared CLI output layer, injected via ``ctx.obj.render``.

    Thin wrapper around the module-level ``console`` so every command
    prints through the same Rich console. Methods for message primitives
    replace inline ``[red]…[/red]`` markup; table/KV helpers replace
    repeated scaffolding.
    """

    def __init__(self, con: Console = console) -> None:
        self.con = con

    # ------------------------------------------------------------------
    # message primitives — drop-in replacements for [red]/[green] markup
    # ------------------------------------------------------------------

    def success(self, message: str) -> None:
        self.con.print(f"[{Style.SUCCESS}]{message}[/{Style.SUCCESS}]")

    def error(self, message: str) -> None:
        self.con.print(f"[{Style.ERROR}]{message}[/{Style.ERROR}]")

    def warn(self, message: str) -> None:
        self.con.print(f"[{Style.WARN}]{message}[/{Style.WARN}]")

    def info(self, message: str) -> None:
        self.con.print(f"[{Style.INFO}]{message}[/{Style.INFO}]")

    def dim(self, message: str) -> None:
        self.con.print(f"[{Style.DIM}]{message}[/{Style.DIM}]")

    def print(self, *args: RenderableType) -> None:
        """Pass-through to ``con.print`` for escape-hatch / structured output."""
        self.con.print(*args)

    # ------------------------------------------------------------------
    # value helpers — replace magic strings
    # ------------------------------------------------------------------

    @staticmethod
    def na(value: JsonValue) -> str:
        """Return *NA* placeholder when *value* is None / empty."""
        return str(value) if value not in (None, "", []) else NA

    @staticmethod
    def check(flag: bool) -> Text:
        """Return a checkmark for True, a dot for False."""
        return Text("✓", style=Style.SUCCESS) if flag else Text("·", style=Style.DIM)

    @staticmethod
    def event_style(event_type: str) -> str:
        """Resolve a ``EventType`` string to a Rich style."""
        return EVENT_STYLES.get(event_type, "white")

    # ------------------------------------------------------------------
    # structural helpers — replace repeated Table / Panel scaffolding
    # ------------------------------------------------------------------

    def table(
        self,
        title: str,
        *columns: str,
        header_style: str = Style.HEADER,
    ) -> Table:
        """Build a Rich Table with house styling.

        Caller adds rows via ``table.add_row(…)``, then calls
        ``ctx.obj.render.print(table)`` to display.
        """
        t = Table(title=title, title_style="bold", header_style=header_style)
        for col in columns:
            t.add_column(col)
        return t

    def kv(
        self,
        title: str,
        pairs: Sequence[tuple[str, str]],
        *,
        border: str = Style.INFO,
    ) -> None:
        """Display a two-column key-value panel.

        *pairs* is a list of ``(key, value)`` tuples.
        """
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", justify="right")
        grid.add_column()
        for k, v in pairs:
            grid.add_row(k, v)
        self.con.print(Panel(grid, title=title, border_style=border))

    def syntax(
        self,
        code: str,
        lexer: str,
        *,
        theme: str = "monokai",
        line_numbers: bool = False,
    ) -> None:
        """Print syntax-highlighted code."""
        self.con.print(Syntax(code, lexer, theme=theme, line_numbers=line_numbers))

    def json(self, data: str | JsonValue) -> None:
        """Print pretty JSON (accepts a str of JSON or any dumpable object)."""
        self.con.print(JSON(data) if isinstance(data, str) else JSON.from_data(data))

    def panel(
        self,
        body: RenderableType,
        *,
        title: str | None = None,
        border: str = Style.INFO,
    ) -> None:
        """Print a Rich Panel with optional title and border style."""
        self.con.print(Panel(body, title=title, border_style=border))
