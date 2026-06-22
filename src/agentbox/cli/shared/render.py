"""CLI rendering helpers — reusable output/formatting layer.

Every command accesses a shared ``Renderer`` via ``ctx.obj.render``.
Common output operations (success/error/warn/dim messages, tables, KV
panels) live here so command bodies can stop writing inline Rich markup
and magic strings. The single ``Console`` instance in ``common.py`` is
reused — no second console is created.
"""

from __future__ import annotations

from typing import Any, Sequence

from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from rich.text import Text

from agentbox.cli.shared.common import console
from agentbox.cli.shared.constants import NA, EVENT_STYLES, Style


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

    def print(self, *args: Any, **kwargs: Any) -> None:
        """Pass-through to ``con.print`` for escape-hatch / structured output."""
        self.con.print(*args, **kwargs)

    # ------------------------------------------------------------------
    # value helpers — replace magic strings
    # ------------------------------------------------------------------

    @staticmethod
    def na(value: object) -> str:
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
