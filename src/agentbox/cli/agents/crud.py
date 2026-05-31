from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli._deps import get_settings, get_store
from agentbox.cli._common import console, handle_cli_errors, resolve_agent
from agentbox.core import prompts
from agentbox.core.service import (
    branch_agent_draft,
    clear_agent_runner_profile,
    create_agent,
    create_agent_version,
    get_agent_def,
    get_agent_runner_profile,
    get_prompt_version,
    get_runner_profile,
    latest_agent_version,
    publish_agent_version,
    rollback_agent_to,
    set_agent_runner_profile,
    soft_delete_agent,
)
from agentbox.core.service.agents import list_all_agents

agent_app = typer.Typer(
    name="agent",
    help="Inspect agent definitions and prompts.",
    no_args_is_help=True,
)


@agent_app.command("ls")
def agent_ls(
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """List agents registered in the DB."""
    store = get_store()
    rows = list_all_agents(store=store)

    if json_output:
        console.print(
            json.dumps(
                [a.model_dump(mode="json") for a in rows], indent=2
            )
        )
        return

    if not rows:
        console.print("[yellow]No agents registered.[/yellow]")
        return

    table = Table(
        title="Agents",
        title_style="bold",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
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
        # Model is resolved via the bound runner profile — the legacy
        # ``runner.model`` field is no longer surfaced.
        profile = get_agent_runner_profile(store, a.id)
        model_display = (profile.model if profile else None) or "[dim]default[/dim]"
        table.add_row(
            a.id,
            a.runner.kind,
            model_display,
            a.session_mode,
            ws_display,
            a.description or "",
        )
    console.print(table)


@agent_app.command("show")
def agent_show(agent_id: str) -> None:
    """Show the full resolved AgentDef for an agent."""
    a = resolve_agent(agent_id)

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("id", a.id)
    meta.add_row("description", a.description or "—")
    meta.add_row("source_format", a.source_format.value if a.source_format else "—")
    meta.add_row("source_path", str(a.source_path) if a.source_path else "—")
    meta.add_row("tags", ", ".join(a.tags) if a.tags else "—")
    console.print(Panel(meta, title="Meta", border_style="cyan"))

    runner = Table.grid(padding=(0, 2))
    runner.add_column(style="dim", justify="right")
    runner.add_column()
    runner.add_row("kind", a.runner.kind)
    # The model is owned by the bound runner profile. The legacy
    # ``runner.model`` field is no longer displayed — see the "Runner
    # profile" panel below for the authoritative model.
    runner.add_row("timeout", f"{a.runner.timeout_seconds}s")
    runner.add_row(
        "allowed_tools",
        ", ".join(a.runner.allowed_tools) if a.runner.allowed_tools else "—",
    )
    runner.add_row("mcp_config_path", a.runner.mcp_config_path or "—")
    console.print(Panel(runner, title="Runner", border_style="green"))

    profile = get_agent_runner_profile(get_store(), a.id)
    rp = Table.grid(padding=(0, 2))
    rp.add_column(style="dim", justify="right")
    rp.add_column()
    if profile is None:
        rp.add_row("bound profile", "[dim](none — system default)[/dim]")
    else:
        rp.add_row("id", profile.id)
        rp.add_row("name", profile.name)
        rp.add_row("backend", profile.backend)
        rp.add_row("provider", profile.provider or "—")
        rp.add_row("model", profile.model or "—")
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


@agent_app.command("prompt")
def agent_prompt(
    agent_id: str,
    version: int | None = typer.Option(
        None, "--version", help="Prompt version to display"
    ),
) -> None:
    """Print the agent's system prompt."""
    a = resolve_agent(agent_id)
    settings = get_settings()
    store = get_store()

    if version is not None:
        committed = get_prompt_version(store, agent_id, version)
        if committed is None:
            console.print(
                f"[red]version {version} not found for agent {agent_id!r}[/red]"
            )
            raise typer.Exit(2)
        content = committed["content"]
    else:
        doc = prompts.read_versioned(a, settings.project_root, store)
        content = doc.content

    if not content:
        console.print("[yellow]No prompt content for this agent.[/yellow]")
        return

    console.print(Syntax(content, "markdown", theme="ansi_dark"))


# ---------------------------------------------------------------------------
# Plan 18 — DB-only write commands. These talk to the store directly so they
# work in offline contexts (no HTTP server required).
# ---------------------------------------------------------------------------


def _set_dotted(obj: dict, dotted: str, value: object) -> None:
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
    """Try JSON first (so ``[1,2]`` / ``true`` parse), else return the str."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@agent_app.command("create")
def agent_create(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        exists=True,
        readable=True,
        help="Path to inline JSON config (full AgentDef shape).",
    ),
    author: str = typer.Option(..., "--author"),
    changelog: str = typer.Option(
        "initial draft", "--changelog", help="Changelog (min 3 chars)."
    ),
) -> None:
    """Create a new DB-only agent from an inline JSON config file.

    The config file must be a JSON object matching ``AgentDef``. No on-disk
    backing file is created; the agent lives entirely in the DB.
    """
    from agentbox.core.agent.config import build_config_json_payload
    from agentbox.core.data import AgentDef

    data = json.loads(config.read_text(encoding="utf-8"))
    try:
        agent_def = AgentDef.model_validate(data)
    except Exception as exc:
        console.print(f"[red]invalid AgentDef:[/red] {exc}")
        raise typer.Exit(2) from exc

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


@agent_app.command("edit")
def agent_edit(
    agent_id: str,
    set_: list[str] = typer.Option(
        [],
        "--set",
        "-s",
        help="dotted=value pairs, e.g. runner.kind=token. Repeatable.",
    ),
    author: str = typer.Option("cli", "--author"),
    changelog: str = typer.Option("cli edit", "--changelog"),
) -> None:
    """Edit an agent in the DB. Each ``--set k=v`` overrides a field.

    Values are parsed as JSON when possible (so ``--set tags='["x","y"]'``
    works), else stored verbatim as a string.
    """
    import hashlib

    from agentbox.core.data import AgentDef
    from agentbox.core.agent.prompt.versioning.drift import _build_snapshot

    if not set_:
        console.print("[red]nothing to set; pass --set k=v[/red]")
        raise typer.Exit(2)

    store = get_store()
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
    snapshot = _build_snapshot(updated)
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
        content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
        author=author,
        changelog=changelog,
        files=None,
    )
    console.print(
        f"[green]new version[/green] {updated.id!r} v{rec['version']} "
        f"(draft={rec.get('is_draft', False)}) — publish with `agent publish`"
    )


@agent_app.command("delete")
def agent_delete(
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
# Agent lifecycle — draft, publish, rollback
# ---------------------------------------------------------------------------


@agent_app.command("draft")
def agent_draft(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Create a new draft version by cloning the active version."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = branch_agent_draft(store, agent_id, author=author)
    console.print(
        f"[green]draft created[/green] v{result.get('version')} "
        f"(id={result.get('id')}, draft={result.get('is_draft', True)})"
    )


@agent_app.command("publish")
def agent_publish(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number to publish"),
    reason: str = typer.Option("cli publish", "--reason", help="Publish reason"),
) -> None:
    """Publish a draft version (set as active)."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = publish_agent_version(store, agent_id, version, reason)
    console.print(
        f"[green]published[/green] v{result.get('version')} "
        f"(id={result.get('id')})"
    )


@agent_app.command("rollback")
def agent_rollback(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Target version to roll back to"),
    reason: str = typer.Option(..., "--reason", help="Rollback reason (min 3 chars)"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Roll back to a previous agent version (creates a new version)."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = rollback_agent_to(store, agent_id, version, reason, author=author)
    console.print(
        f"[green]rolled back[/green] to v{version} (new v{result.get('version')})"
    )


# ---------------------------------------------------------------------------
# Runner profile binding
# ---------------------------------------------------------------------------


@agent_app.command("runner-profile")
def agent_runner_profile(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    get: bool = typer.Option(False, "--get", help="Show the bound runner profile"),
    set_: str | None = typer.Option(
        None, "--set", help="Runner profile ID to bind"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="Remove the runner profile binding"
    ),
) -> None:
    """Get, set, or clear the runner profile bound to an agent.

    Examples:
        agents runner-profile my-agent --get
        agents runner-profile my-agent --set <profile_id>
        agents runner-profile my-agent --clear
    """
    if sum([get, set_ is not None, clear]) != 1:
        console.print(
            "[red]exactly one of --get, --set, or --clear must be specified[/red]"
        )
        raise typer.Exit(2)

    resolve_agent(agent_id)
    store = get_store()

    if get:
        profile = get_agent_runner_profile(store, agent_id)
        if profile is None:
            console.print("[dim]no runner profile bound[/dim]")
        else:
            console.print(
                f"[bold]{profile.id}[/bold] — {profile.name} "
                f"([cyan]{profile.backend}[/cyan] / {profile.provider or 'default'})"
            )
    elif set_:
        profile = get_runner_profile(store, set_)
        if profile is None:
            console.print(f"[red]runner profile {set_!r} not found[/red]")
            raise typer.Exit(1)
        set_agent_runner_profile(store, agent_id, set_)
        console.print(f"[green]bound[/green] profile {set_!r} to {agent_id!r}")
    elif clear:
        clear_agent_runner_profile(store, agent_id)
        console.print(f"[yellow]cleared[/yellow] profile binding for {agent_id!r}")


# ---------------------------------------------------------------------------
# Version files
# ---------------------------------------------------------------------------


@agent_app.command("files")
def agent_files(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    add: bool = typer.Option(False, "--add", help="Add a file to the version"),
    rm: int | None = typer.Option(
        None, "--rm", help="File ID to remove from the version"
    ),
    kind: str | None = typer.Option(
        None, "--kind", help="File kind (output_schema, input_schema, etc.)"
    ),
    name: str | None = typer.Option(
        None, "--name", help="File name for --add"
    ),
    content: str | None = typer.Option(
        None, "--content", help="File content for --add"
    ),
) -> None:
    """Add or remove version bundle files.

    Examples:
        agents files my-agent 1 --add --kind output_schema --name schema.json --content '{"...""}'
        agents files my-agent 1 --rm 42
    """
    from agentbox.core.service.agents import (
        delete_version_file,
        upload_version_file,
    )
    from agentbox.core.service.agents import (
        VersionFileNotFound,
        VersionNotDraft,
        VersionNotFound,
    )

    if add and rm is not None:
        console.print("[red]use --add or --rm, not both[/red]")
        raise typer.Exit(2)
    if not add and rm is None:
        console.print("[red]use --add or --rm[/red]")
        raise typer.Exit(2)

    store = get_store()

    if add:
        if not kind or not name or not content:
            console.print(
                "[red]--kind, --name, and --content required for --add[/red]"
            )
            raise typer.Exit(2)
        try:
            result = upload_version_file(
                store=store,
                agent_id=agent_id,
                version=version,
                kind=kind,
                name=name,
                content=content,
            )
        except VersionNotFound:
            console.print(f"[red]version {version} not found[/red]")
            raise typer.Exit(1)
        except VersionNotDraft as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)
        except Exception as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)
        console.print(
            f"[green]added[/green] {name!r} (file_id={result['file']['id']}, "
            f"sha256={result['sha256'][:8]})"
        )
    elif rm is not None:
        try:
            delete_version_file(
                store=store,
                agent_id=agent_id,
                version=version,
                file_id=rm,
            )
        except VersionNotFound:
            console.print(f"[red]version {version} not found[/red]")
            raise typer.Exit(1)
        except VersionNotDraft:
            console.print("[red]version is not a draft[/red]")
            raise typer.Exit(1)
        except VersionFileNotFound:
            console.print(f"[red]file {rm} not found[/red]")
            raise typer.Exit(1)
        console.print(f"[yellow]removed[/yellow] file {rm} from v{version}")
