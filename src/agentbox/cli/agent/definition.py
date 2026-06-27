"""Agent definitions — ls, show, new, edit, rm, export."""

from __future__ import annotations

import json
from pathlib import Path

import tomlkit
import typer

from agentbox.cli.shared import CliCtx, resolve_agent
# TODO(cli-arch): build_* free-fns — candidate AgentService create_version helpers
from agentbox.core.service import AgentDef, build_agent_snapshot, build_config_json_payload
from agentbox.core.service.engines.service import ProfileNotFound

# TODO(cli-arch): AgentService.list_all
from agentbox.core.service.agents import list_all_agents


# TODO(cli-arch): candidate AgentService export/import methods
def _set_dotted(obj: dict[str, object], dotted: str, value: object) -> None:
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


def _list_agent_ids(obj: CliCtx) -> list[str]:
    # TODO(cli-arch): AgentService.list_all ids
    rows = obj.store.list_agents_with_latest()
    return [r["agent_id"] for r in rows]


# TODO(cli-arch): candidate AgentService export/import methods
def _export_one(agent: AgentDef, base: Path, obj: CliCtx) -> None:
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
    obj.render.agent.dim(f"  {toml_path}")

    if prompt:
        prompt_path = base / f"{agent.id}.prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        obj.render.agent.dim(f"  {prompt_path}")


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
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """List agents registered in the DB."""
    obj: CliCtx = ctx.obj
    rows = list_all_agents(store=obj.store)  # TODO(cli-arch): AgentService.list_all

    if json_output:
        obj.render.agent.agents_json(
            [a.model_dump(mode="json") for a in rows]
        )
        return

    table_rows: list[dict[str, object]] = []
    for a in rows:
        ws_display = (
            "[yellow]<ephemeral>[/yellow]"
            if a.workspace == "<ephemeral>"
            else (a.workspace or "[dim]auto[/dim]")
        )
        profile = obj.engines.get_agent_runner_profile(a.id)
        model_display = (
            (profile.model if profile else None) or "[dim]default[/dim]"
        )
        table_rows.append({
            "id": a.id,
            "runner_kind": a.runner.kind,
            "model": model_display,
            "session_mode": a.session_mode,
            "workspace": ws_display,
            "description": a.description or "",
        })
    obj.render.agent.agents_table(table_rows)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@definition_app.command("show")
def def_show(ctx: typer.Context, agent_id: str) -> None:
    """Show the full resolved AgentDef for an agent."""
    obj: CliCtx = ctx.obj
    a = resolve_agent(agent_id)

    obj.render.agent.agent_meta_panel(a)
    obj.render.agent.agent_runner_panel(a)

    profile = obj.engines.get_agent_runner_profile(a.id)
    profile_dict: dict[str, object] | None
    if profile is None:
        profile_dict = None
    else:
        profile_dict = {
            "id": profile.id,
            "name": profile.name,
            "backend": profile.backend,
            "provider": profile.provider or None,
            "model": profile.model or None,
        }
    obj.render.agent.agent_profile_panel(profile_dict)
    obj.render.agent.agent_workspace_panel(a)

    servers = obj.system.get_project_mcp_servers()
    obj.render.agent.agent_mcp_servers_panel(servers)


# ---------------------------------------------------------------------------
# new (was: create)
# ---------------------------------------------------------------------------


@definition_app.command("new")
def def_new(
    ctx: typer.Context,
    name: str = typer.Option(
        "",
        "--name",
        "-n",
        help="Agent id + display name. Creates a minimal agent with sensible defaults.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        exists=True,
        readable=True,
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
    obj: CliCtx = ctx.obj

    if config is not None:
        data = json.loads(config.read_text(encoding="utf-8"))
        try:
            agent_def = AgentDef.model_validate(data)
        except Exception as exc:
            obj.render.agent.error(f"invalid AgentDef: {exc}")
            raise typer.Exit(2) from exc
    elif name:
        agent_def = AgentDef(id=name, description=name)
    else:
        obj.render.agent.error("either --config or --name is required")
        raise typer.Exit(2)

    if obj.agents.latest_version(agent_def.id) is not None:
        obj.render.agent.error(f"agent {agent_def.id!r} already exists")
        raise typer.Exit(1)

    rec = obj.agents.create_agent(
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
    obj.render.agent.agent_created(agent_def.id, rec["version"], rec["id"])


# ---------------------------------------------------------------------------
# edit (with --runner for profile binding)
# ---------------------------------------------------------------------------


@definition_app.command("edit")
def def_edit(
    ctx: typer.Context,
    agent_id: str,
    set_: list[str] = typer.Option(
        [],
        "--set",
        "-s",
        help="dotted=value pairs, e.g. runner.kind=token. Repeatable.",
    ),
    runner: str | None = typer.Option(
        None,
        "--runner",
        help="Runner profile ID to bind (set). Use 'clear' to unbind.",
    ),
    author: str = typer.Option("cli", "--author"),
    changelog: str = typer.Option("cli edit", "--changelog"),
) -> None:
    """Edit an agent in the DB. Each ``--set k=v`` overrides a field.

    Use ``--runner <profile_id>`` to bind a runner profile, or
    ``--runner clear`` to unbind.
    """
    obj: CliCtx = ctx.obj

    # -- runner profile binding
    if runner is not None:
        resolve_agent(agent_id)
        if runner == "clear":
            obj.engines.clear_agent_runner_profile(agent_id)
            obj.render.agent.profile_cleared(agent_id)
        else:
            try:
                obj.engines.get_profile(runner)
            except ProfileNotFound:
                obj.render.agent.error(f"runner profile {runner!r} not found")
                raise typer.Exit(1)
            obj.engines.set_agent_runner_profile(agent_id, runner)
            obj.render.agent.profile_bound(runner, agent_id)

    # -- dotted field edits
    if not set_ and runner is None:
        obj.render.agent.error("nothing to set; pass --set k=v or --runner")
        raise typer.Exit(2)

    if not set_:
        return

    current = obj.agents.get_agent_def(agent_id)
    if current is None:
        obj.render.agent.error(f"agent {agent_id!r} not found")
        raise typer.Exit(1)

    merged = current.model_dump(mode="python")
    for pair in set_:
        if "=" not in pair:
            obj.render.agent.error(f"bad --set pair: {pair!r}")
            raise typer.Exit(2)
        k, v = pair.split("=", 1)
        _set_dotted(merged, k.strip(), _coerce(v.strip()))

    try:
        updated = AgentDef.model_validate(merged)
    except Exception as exc:
        obj.render.agent.error(f"validation failed: {exc}")
        raise typer.Exit(2) from exc

    updated.source_path = current.source_path
    updated.source_format = current.source_format
    snapshot = build_agent_snapshot(updated)
    prompt_text = ""
    if updated.prompt_path:
        try:
            prompt_text = updated.load_prompt(obj.settings.project_root)
        except FileNotFoundError:
            prompt_text = ""

    rec = obj.agents.create_version(
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
    obj.render.agent.version_edit_new(updated.id, rec["version"])


# ---------------------------------------------------------------------------
# rm (was: delete)
# ---------------------------------------------------------------------------


@definition_app.command("rm")
def def_rm(
    ctx: typer.Context,
    agent_id: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Soft-delete an agent. Version history is retained."""
    obj: CliCtx = ctx.obj
    if not yes:
        confirm = typer.confirm(
            f"Soft-delete agent {agent_id!r}? (history retained)"
        )
        if not confirm:
            raise typer.Exit(0)
    result = obj.agents.soft_delete(agent_id)
    if result is None:
        obj.render.agent.agent_not_found(agent_id)
        raise typer.Exit(1)
    obj.render.agent.agent_deleted(agent_id)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@definition_app.command("export")
def def_export(
    ctx: typer.Context,
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
    obj: CliCtx = ctx.obj
    base = Path(out_dir).expanduser()

    if agent_id:
        agent = obj.agents.get_agent_def(agent_id)
        if agent is None:
            obj.render.agent.agent_not_found(agent_id)
            raise typer.Exit(1)
        _export_one(agent, base, obj)
    else:
        agents = _list_agent_ids(obj)
        if not agents:
            obj.render.agent.warn("no agents found")
            return
        for aid in agents:
            agent = obj.agents.get_agent_def(aid)
            if agent is None:
                continue
            _export_one(agent, base, obj)
    obj.render.agent.agent_exported(str(base.resolve()))