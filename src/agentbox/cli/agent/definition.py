"""Agent definitions — ls, show, new, edit, rm, export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tomlkit
import typer
from rich.panel import Panel
from rich.table import Table

from agentbox.cli.shared import console, resolve_agent, get_settings, get_store
from agentbox.core.db import SessionStore
from agentbox.core.service import (
    AgentDef,
    build_agent_snapshot,
    build_config_json_payload,
    clear_agent_runner_profile,
    create_agent,
    create_agent_version,
    get_agent_def,
    get_agent_runner_profile,
    get_runner_profile,
    latest_agent_version,
    set_agent_runner_profile,
    soft_delete_agent,
)
from agentbox.core.service.agents import list_all_agents


def _set_dotted(obj: dict[str, Any], dotted: str, value: object) -> None:
    """Set a nested key using dot notation on a dict."""
    parts = dotted.split(".")
    cur = obj
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _coerce(value: str) -> object:
    """Try JSON first, else return the str."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


definition_app = typer.Typer(
    name="def",
    help="List, show, create, edit, delete, and export agents.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# ls
# ---------------------------------------------------------------------------


@definition_app.command("ls")
def def_ls(
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """List agents registered in the DB."""
    store = get_store()
    rows = list_all_agents(store=store)

    if json_output:
        console.print(
            json.dumps([a.model_dump(mode="json") for a in rows], indent=2)
        )
        return

    if not rows:
        console.print("[yellow]No agents registered.[/yellow]")
        return

    table = Table(
        title="Agents", title_style="bold", header_style="bold cyan",
        show_lines=False, padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Runner", style="cyan")
    table.add_column("Model", style="dim")
    table.add_column("Session", style="dim")
    table.add_column("Workspace", style="dim")
    table.add_column("Description")

    for a in rows:
        ws_display = (
            "[yellow]<ephemeral>[/yellow]"
            if a.workspace == "<ephemeral>"
            else (a.workspace or "[dim]auto[/dim]")
        )
        profile = get_agent_runner_profile(store, a.id)
        model_display = (profile.model if profile else None) or "[dim]default[/dim]"
        table.add_row(
            a.id, a.runner.kind, model_display,
            a.session_mode, ws_display, a.description or "",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@definition_app.command("show")
def def_show(agent_id: str) -> None:
    """Show the full resolved AgentDef for an agent."""
    a = resolve_agent(agent_id)

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("id", a.id)
    meta.add_row("description", a.description or "\u2014")
    meta.add_row("source_format", a.source_format.value if a.source_format else "\u2014")
    meta.add_row("source_path", str(a.source_path) if a.source_path else "\u2014")
    meta.add_row("tags", ", ".join(a.tags) if a.tags else "\u2014")
    console.print(Panel(meta, title="Meta", border_style="cyan"))

    runner = Table.grid(padding=(0, 2))
    runner.add_column(style="dim", justify="right")
    runner.add_column()
    runner.add_row("kind", a.runner.kind)
    runner.add_row("timeout", f"{a.runner.timeout_seconds}s")
    runner.add_row(
        "allowed_tools",
        ", ".join(a.runner.allowed_tools) if a.runner.allowed_tools else "\u2014",
    )
    runner.add_row("mcp_config_path", a.runner.mcp_config_path or "\u2014")
    console.print(Panel(runner, title="Runner", border_style="green"))

    profile = get_agent_runner_profile(get_store(), a.id)
    rp = Table.grid(padding=(0, 2))
    rp.add_column(style="dim", justify="right")
    rp.add_column()
    if profile is None:
        rp.add_row("bound profile", "[dim](none \u2014 system default)[/dim]")
    else:
        rp.add_row("id", profile.id)
        rp.add_row("name", profile.name)
        rp.add_row("backend", profile.backend)
        rp.add_row("provider", profile.provider or "\u2014")
        rp.add_row("model", profile.model or "\u2014")
    console.print(Panel(rp, title="Runner profile", border_style="green"))

    ws = Table.grid(padding=(0, 2))
    ws.add_column(style="dim", justify="right")
    ws.add_column()
    ws.add_row("workspace", a.workspace or "[dim]auto[/dim]")
    ws.add_row("session_mode", a.session_mode)
    ws.add_row("headless", str(a.headless))
    ws.add_row("claude_agent", str(a.claude_agent))
    console.print(Panel(ws, title="Workspace", border_style="blue"))

    servers = get_store().get_project_mcp_servers()
    if servers:
        mcp_list = Table.grid(padding=(0, 2))
        mcp_list.add_column(style="dim")
        mcp_list.add_column()
        for s in servers:
            mcp_list.add_row(s.name, s.url or " ".join(s.command or []))
        console.print(Panel(mcp_list, title="MCP Servers", border_style="yellow"))


# ---------------------------------------------------------------------------
# new (was: create)
# ---------------------------------------------------------------------------


@definition_app.command("new")
def def_new(
    name: str = typer.Option(
        "",
        "--name", "-n",
        help="Agent id + display name. Creates a minimal agent with sensible defaults.",
    ),
    config: Path | None = typer.Option(
        None, "--config", "-c",
        exists=True, readable=True,
        help="Path to inline JSON config (full AgentDef shape).",
    ),
    author: str = typer.Option("cli", "--author", help="Author identifier."),
    changelog: str = typer.Option(
        "initial draft", "--changelog", help="Changelog (min 3 chars)."
    ),
) -> None:
    """Create a new DB-only agent.

    Use ``--config`` to load a full AgentDef JSON file, or ``--name``
    to create a minimal agent with sensible defaults.
    """
    if config is not None:
        data = json.loads(config.read_text(encoding="utf-8"))
        try:
            agent_def = AgentDef.model_validate(data)
        except Exception as exc:
            console.print(f"[red]invalid AgentDef:[/red] {exc}")
            raise typer.Exit(2) from exc
    elif name:
        agent_def = AgentDef(id=name, description=name)
    else:
        console.print("[red]either --config or --name is required[/red]")
        raise typer.Exit(2)

    store = get_store()
    if latest_agent_version(store, agent_def.id) is not None:
        console.print(f"[red]agent {agent_def.id!r} already exists[/red]")
        raise typer.Exit(1)

    rec = create_agent(
        store,
        agent_id=agent_def.id,
        config_json={
            **agent_def.model_dump(mode="json", exclude_none=True),
            **build_config_json_payload(agent_def),
        },
        prompt_content=agent_def.prompt,
        author=author,
        changelog=changelog,
        source="cli",
        sync_mode="off",
        export_to_disk=False,
    )
    console.print(
        f"[green]created[/green] {agent_def.id!r} v{rec['version']} "
        f"(draft, version_id={rec['id']})"
    )


# ---------------------------------------------------------------------------
# edit (with --runner for profile binding)
# ---------------------------------------------------------------------------


@definition_app.command("edit")
def def_edit(
    agent_id: str,
    set_: list[str] = typer.Option(
        [], "--set", "-s",
        help="dotted=value pairs, e.g. runner.kind=token. Repeatable.",
    ),
    runner: str | None = typer.Option(
        None, "--runner",
        help="Runner profile ID to bind (set). Use 'clear' to unbind.",
    ),
    author: str = typer.Option("cli", "--author"),
    changelog: str = typer.Option("cli edit", "--changelog"),
) -> None:
    """Edit an agent in the DB. Each ``--set k=v`` overrides a field.

    Use ``--runner <profile_id>`` to bind a runner profile, or
    ``--runner clear`` to unbind.
    """
    store = get_store()

    # -- runner profile binding
    if runner is not None:
        resolve_agent(agent_id)
        if runner == "clear":
            clear_agent_runner_profile(store, agent_id)
            console.print(f"[yellow]cleared[/yellow] profile binding for {agent_id!r}")
        else:
            profile = get_runner_profile(store, runner)
            if profile is None:
                console.print(f"[red]runner profile {runner!r} not found[/red]")
                raise typer.Exit(1)
            set_agent_runner_profile(store, agent_id, runner)
            console.print(f"[green]bound[/green] profile {runner!r} to {agent_id!r}")

    # -- dotted field edits
    if not set_ and runner is None:
        console.print("[red]nothing to set; pass --set k=v or --runner[/red]")
        raise typer.Exit(2)

    if not set_:
        return

    settings = get_settings()
    current = get_agent_def(store, agent_id)
    if current is None:
        console.print(f"[red]agent {agent_id!r} not found[/red]")
        raise typer.Exit(1)

    merged = current.model_dump(mode="python")
    for pair in set_:
        if "=" not in pair:
            console.print(f"[red]bad --set pair: {pair!r}[/red]")
            raise typer.Exit(2)
        k, v = pair.split("=", 1)
        _set_dotted(merged, k.strip(), _coerce(v.strip()))

    try:
        updated = AgentDef.model_validate(merged)
    except Exception as exc:
        console.print(f"[red]validation failed:[/red] {exc}")
        raise typer.Exit(2) from exc

    updated.source_path = current.source_path
    updated.source_format = current.source_format
    snapshot = build_agent_snapshot(updated)
    prompt_text = ""
    if updated.prompt_path:
        try:
            prompt_text = updated.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""

    rec = create_agent_version(
        store,
        agent_id=updated.id,
        source_path=str(updated.source_path) if updated.source_path else "",
        source_format=(
            updated.source_format.value if updated.source_format else "unknown"
        ),
        content_snapshot=snapshot,
        prompt_snapshot=prompt_text,
        content_hash=__import__("hashlib").sha256(snapshot.encode("utf-8")).hexdigest(),
        author=author,
        changelog=changelog,
        files=None,
    )
    console.print(
        f"[green]new version[/green] {updated.id!r} v{rec['version']} "
        "\u2014 publish with `agent version publish`"
    )


# ---------------------------------------------------------------------------
# rm (was: delete)
# ---------------------------------------------------------------------------


@definition_app.command("rm")
def def_rm(
    agent_id: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Soft-delete an agent. Version history is retained."""
    if not yes:
        confirm = typer.confirm(f"Soft-delete agent {agent_id!r}? (history retained)")
        if not confirm:
            raise typer.Exit(0)
    store = get_store()
    result = soft_delete_agent(store, agent_id)
    if result is None:
        console.print(f"[red]agent {agent_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[green]deleted[/green] {agent_id!r}")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def _list_agent_ids(store: SessionStore) -> list[str]:
    rows = store.list_agents_with_latest()
    return [r["agent_id"] for r in rows]


def _export_one(agent: AgentDef, base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    prompt = agent.prompt
    agent_dump = agent.model_dump(mode="json", exclude_none=True)
    agent_dump.pop("prompt", None)
    agent_dump.pop("headless", None)
    agent_dump.pop("claude_agent", None)

    toml_path = base / f"{agent.id}.toml"
    doc = tomlkit.document()
    doc.add(tomlkit.comment(f" Exported from agentbox \u2014 {agent.id}"))
    for key, value in agent_dump.items():
        doc[key] = value
    toml_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    console.print(f"  [dim]{toml_path}[/dim]")

    if prompt:
        prompt_path = base / f"{agent.id}.prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        console.print(f"  [dim]{prompt_path}[/dim]")


@definition_app.command("export")
def def_export(
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Export a single agent. Omit to export all."
    ),
    out_dir: str = typer.Option(
        ".", "--out", "-o", help="Output directory (default: current directory)."
    ),
) -> None:
    """Export DB agents to on-disk TOML files.

    Writes ``<agent_id>.toml`` and (if the agent has a prompt)
    ``<agent_id>.prompt.md`` into ``--out``. Idempotent.
    """
    store = get_store()
    base = Path(out_dir).expanduser()

    if agent_id:
        agent = get_agent_def(store, agent_id)
        if agent is None:
            console.print(f"[red]agent {agent_id!r} not found[/red]")
            raise typer.Exit(1)
        _export_one(agent, base)
    else:
        agents = _list_agent_ids(store)
        if not agents:
            console.print("[yellow]no agents found[/yellow]")
            return
        for aid in agents:
            agent = get_agent_def(store, aid)
            if agent is None:
                continue
            _export_one(agent, base)
    console.print(f"[green]done[/green] \u2192 {base.resolve()}")
