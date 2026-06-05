"""Unified credential bootstrap — ``agentbox ops creds``."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import typer
from rich.table import Table
from rich.text import Text

from agentbox.cli._common import console
from agentbox.core.engines.credentials import (
    CredentialMethod,
    CredentialState,
    Method,
    get as creds_get,
    list_all as creds_list_all,
)

from agentbox.core.engines.credentials import _registration  # noqa: F401

creds_app = typer.Typer(
    name="creds",
    help="Credential management: setup, status, import, clear.",
    no_args_is_help=True,
)

_CREDS_BASE = Path(os.environ.get("AGENTBOX_CREDS_DIR", "/agentbox/creds"))
_ENV_FILE = _CREDS_BASE / ".env"


@creds_app.command()
def setup(
    name: str | None = typer.Argument(
        None,
        help="Backend name to set up (e.g. claude, opencode, openai). Omit for interactive walkthrough.",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        help="Try every registered backend, skip none.",
    ),
) -> None:
    """Interactive credential setup walkthrough."""
    all_items = creds_list_all()
    if not all_items:
        console.print("[dim]No credential backends registered.[/dim]")
        return
    if name:
        cm = creds_get(name)
        if cm is None:
            console.print(f"[red]Unknown backend:[/red] {name!r}")
            raise typer.Exit(1)
        _setup_one(cm, skip_choice=all)
        return
    if all:
        for cm in all_items:
            _setup_one(cm, skip_choice=True)
        return
    _interactive_setup(all_items)


def _interactive_setup(items: list[CredentialMethod]) -> None:
    console.print("\n[bold]Agentbox Credential Setup[/bold]\n")
    for cm in items:
        _setup_one_interactive(cm)


def _setup_one_interactive(cm: CredentialMethod) -> None:
    state = cm.detect()
    state_icon = _state_icon(state)
    console.print(f"\n[{state_icon}]{cm.label}[/{state_icon}] ({cm.backend})")
    if state == CredentialState.PRESENT:
        console.print("  [dim]Credentials detected — skipping. Use `agentbox ops creds clear ...` to reset.[/dim]")
        return
    methods = cm.methods
    if not methods:
        console.print("  [dim]No credential methods available.[/dim]")
        return
    console.print("  Choose method:")
    for i, m in enumerate(methods):
        console.print(f"    {i + 1}) {m.label}")
    choice = typer.prompt("  >", default="s", show_default=False)
    if choice.lower() in ("s", "skip", ""):
        console.print("  [dim]Skipped.[/dim]")
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(methods):
            _apply_method(cm, methods[idx])
        else:
            console.print("  [red]Invalid choice.[/red]")
    except ValueError:
        console.print("  [red]Invalid input — enter a number, or 's' to skip.[/red]")


def _setup_one(cm: CredentialMethod, skip_choice: bool = False) -> None:
    state = cm.detect()
    state_icon = _state_icon(state)
    console.print(f"[{state_icon}]{cm.label}[/{state_icon}] ({cm.backend})")
    if state == CredentialState.PRESENT:
        console.print("  [dim]Already configured.[/dim]")
        return
    methods = cm.methods
    if not methods:
        console.print("  [dim]No credential methods available.[/dim]")
        return
    if skip_choice:
        _apply_method(cm, methods[0])
        return
    if len(methods) == 1:
        _apply_method(cm, methods[0])
    else:
        console.print("  [dim]Multiple methods available; use interactive mode.[/dim]")


def _apply_method(cm: CredentialMethod, method: Method) -> None:
    try:
        ctx: dict = {"creds_base": str(_CREDS_BASE), "env_file": str(_ENV_FILE)}
        method.apply(ctx)
        new_state = cm.detect()
        if new_state == CredentialState.PRESENT:
            console.print(f"  [green]✓[/green] Credential configured via {method.label}")
        else:
            console.print("  [yellow]⚠[/yellow] Method ran but credential not detected. Check manually.")
    except Exception as exc:
        console.print(f"  [red]✗[/red] Failed: {exc}")


@creds_app.command()
def status(
    probe: bool = typer.Option(
        False, "--probe", help="Probe credentials with a lightweight API call."
    ),
) -> None:
    """Show credential status for every registered backend."""
    all_items = creds_list_all()
    if not all_items:
        console.print("[dim]No credential backends registered.[/dim]")
        return
    table = Table(title="Credential Status", title_style="bold", header_style="bold cyan", padding=(0, 2))
    table.add_column("Status", justify="center", width=10)
    table.add_column("Backend", style="bold")
    table.add_column("Detail")
    for cm in all_items:
        state = cm.detect()
        table.add_row(_state_label(state), cm.label, cm.backend)
    console.print(table)


@creds_app.command(name="import")
def import_cmd(
    name: str = typer.Argument(..., help="Backend name to import credentials for (e.g. claude)."),
) -> None:
    """Non-interactive host credential import for a backend."""
    cm = creds_get(name)
    if cm is None:
        console.print(f"[red]Unknown backend:[/red] {name!r}")
        raise typer.Exit(1)
    for m in cm.methods:
        if m.key == "import_host":
            _apply_method(cm, m)
            return
    console.print(f"[red]No import method available for {name!r}.[/red]")
    raise typer.Exit(1)


@creds_app.command(name="clear")
def clear_cmd(
    name: str = typer.Argument(..., help="Backend name to clear credentials for."),
) -> None:
    """Remove stored credentials for one backend."""
    cm = creds_get(name)
    if cm is None:
        console.print(f"[red]Unknown backend:[/red] {name!r}")
        raise typer.Exit(1)
    cleared = False
    oauth_dir = _CREDS_BASE / name
    if oauth_dir.exists():
        shutil.rmtree(oauth_dir)
        console.print(f"[green]Removed:[/green] {oauth_dir}")
        cleared = True
    for child in _CREDS_BASE.iterdir():
        if child.is_dir() and child.name.startswith(f"{name}-"):
            shutil.rmtree(child)
            console.print(f"[green]Removed:[/green] {child}")
            cleared = True
    if _ENV_FILE.exists():
        env_vars = [m.env_var for m in cm.methods if m.env_var]
        if env_vars:
            _remove_env_lines(_ENV_FILE, env_vars)
            console.print(f"[green]Removed env vars from:[/green] {_ENV_FILE}")
            cleared = True
    if not cleared:
        console.print(f"[dim]No credentials found for {name!r}.[/dim]")
    else:
        console.print("[green]Credentials cleared.[/green]")


def _state_icon(state: CredentialState) -> str:
    return {CredentialState.PRESENT: "green", CredentialState.MISSING: "dim", CredentialState.INVALID: "yellow"}.get(state, "dim")


def _state_label(state: CredentialState) -> Text:
    return {
        CredentialState.PRESENT: Text("PRESENT", style="bold green"),
        CredentialState.MISSING: Text("MISSING", style="dim"),
        CredentialState.INVALID: Text("INVALID", style="bold yellow"),
    }.get(state, Text("UNKNOWN", style="dim"))


def _remove_env_lines(env_path: Path, keys: list[str]) -> None:
    if not env_path.exists():
        return
    key_set = set(keys)
    lines = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)\s*=", line)
        if m and m.group(1) in key_set:
            continue
        lines.append(line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
