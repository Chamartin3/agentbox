"""Export agents from DB to on-disk TOML files."""

from __future__ import annotations

from pathlib import Path

import tomlkit
import typer

from agentbox.cli._common import console
from agentbox.cli._deps import get_store
from agentbox.cli.agents.crud import agent_app
from agentbox.core.db import SessionStore
from agentbox.core.service import AgentDef, get_agent_def

@agent_app.command("export")
def agent_export(
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Export a single agent. Omit to export all."
    ),
    out_dir: str = typer.Option(
        ".", "--out", "-o", help="Output directory (default: current directory)."
    ),
) -> None:
    """Export DB agents to on-disk TOML files.

    Writes ``<agent_id>.toml`` and (if the agent has a prompt)
    ``<agent_id>.prompt.md`` into ``--out``. Idempotent — overwrites
    existing files by design.

    When ``--agent`` is omitted, all agents are exported.
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
    console.print(f"[green]done[/green] → {base.resolve()}")


def _list_agent_ids(store: SessionStore) -> list[str]:
    rows = store.list_agents_with_latest()
    return [r["agent_id"] for r in rows]


def _export_one(agent: AgentDef, base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    prompt = agent.prompt
    agent_dump = agent.model_dump(mode="json", exclude_none=True)
    # Remove the inline prompt — it goes to a separate file.
    agent_dump.pop("prompt", None)
    # Remove non-TOML-friendly internals.
    agent_dump.pop("headless", None)
    agent_dump.pop("claude_agent", None)

    toml_path = base / f"{agent.id}.toml"

    doc = tomlkit.document()
    doc.add(tomlkit.comment(f" Exported from agentbox — {agent.id}"))
    for key, value in agent_dump.items():
        doc[key] = value
    toml_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    console.print(f"  [dim]{toml_path}[/dim]")

    if prompt:
        prompt_path = base / f"{agent.id}.prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        console.print(f"  [dim]{prompt_path}[/dim]")
