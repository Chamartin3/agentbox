"""Doctor command — run a suite of diagnostic checks."""

from __future__ import annotations

import typer
from rich.table import Table
from rich.text import Text

from agentbox.cli.shared import console, get_store
from agentbox.core.config import load_settings
from agentbox.core import workspaces as ws_workspaces
from agentbox.core.engines import (
    CredentialState,
    list_backends,
    list_credentials as _creds_list,
)


def doctor() -> None:
    """Run a suite of diagnostic checks and print the results."""
    settings = load_settings()
    table = Table(
        title="Agentbox Doctor", title_style="bold",
        header_style="bold cyan", padding=(0, 2),
    )
    table.add_column("Status", justify="center", width=8)
    table.add_column("Check", style="bold")
    table.add_column("Detail")

    failures = 0
    store = get_store()

    def _ok(check: str, detail: str = "") -> None:
        table.add_row(Text("OK", style="bold green"), check, detail)

    def _warn(check: str, detail: str) -> None:
        table.add_row(Text("WARN", style="bold yellow"), check, detail)

    def _fail(check: str, detail: str) -> None:
        nonlocal failures
        failures += 1
        table.add_row(Text("FAIL", style="bold red"), check, detail)

    path = settings.manifest_path
    if path.exists():
        _ok("Manifest exists", str(path))
    else:
        _fail("Manifest exists", f"not found at {path}")

    try:
        rows = ws_workspaces.list_all(get_store(), settings)
        resolvable = True
        for w in rows:
            if not w.exists and not w.ephemeral:
                resolvable = False
                _warn("Workspaces", f"{w.agent_id}: path {w.path} does not exist")
        if resolvable:
            _ok("Workspaces", f"{len(rows)} agent(s), all paths resolvable")
    except Exception as exc:
        _fail("Workspaces", str(exc))

    try:
        store.list_runs(limit=1)
        _ok("Database", str(settings.db_path))
    except Exception as exc:
        _fail("Database", str(exc))

    try:
        backend_count = len(list_backends())
        _ok("Plugins", f"{backend_count} backend(s)")
    except Exception as exc:
        _fail("Plugins", str(exc))

    try:
        rows = _creds_list()
        if not rows:
            _ok("Credentials", "no backends registered")
        else:
            _ok("Credentials", f"{len(rows)} backend(s)")
            for r in rows:
                state = r.detect()
                label = "configured" if state == CredentialState.PRESENT else "missing"
                if state == CredentialState.PRESENT:
                    _ok(f"  {r.backend}", label)
                else:
                    _warn(f"  {r.backend}", f"{label}")
    except Exception as exc:
        _warn("Credentials", str(exc))

    cache = settings.mcp_cache_dir
    if cache.exists():
        files = list(cache.glob("*.json"))
        _ok("MCP cache", f"{len(files)} cached server(s) in {cache}")
    else:
        _warn("MCP cache", f"cache dir {cache} does not exist")

    console.print(table)
    raise typer.Exit(min(failures, 1))
