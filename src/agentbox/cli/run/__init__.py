"""Unified ``run`` command — one verb for both interactive and headless sessions.

Mode selection
--------------
* ``-p/--prompt TEXT`` or ``--headless`` → headless (POST /api/runs + stream).
* No prompt flag → interactive TTY session via the backend's native CLI.

Positional-argument semantics
------------------------------
* ``AGENT`` (optional) is always an **agent id**. The agent's ``runner.kind``
  determines which backend to launch in interactive mode.
* Ad-hoc interactive with no agent: pass ``--backend/-b {claude|opencode|…}``
  with an optional ``--workspace/-w`` flag.

Validation
----------
* ``--backend`` + ``-p/--prompt`` → error (headless requires an agent, not a backend).
* Interactive + token agent/backend → friendly rejection (token has no CLI).
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx
import typer
import websockets
from rich.panel import Panel

from agentbox.cli.ops.launch import _launch_session
from agentbox.cli.shared import console, event_color, get_store

# Mapping from BackendName values to RunnerKind strings used by _launch_session.
# "token" passes through and is rejected by _launch_session with a clear message.
_BACKEND_NAME_TO_RUNNER: dict[str, str] = {
    "claude_code": "claude",
    "opencode": "opencode",
    "codex": "codex",
    "pi": "pi",
    "token": "token",
}


async def _stream(api: str, run_id: str) -> None:
    ws_url = api.replace("http", "ws") + f"/api/runs/{run_id}/stream"
    async with websockets.connect(ws_url) as ws:
        async for msg in ws:
            ev = json.loads(msg)
            t = ev.get("type", "?")
            style = event_color(t)
            console.print(f"[{style}][{t}][/{style}] {json.dumps(ev)[:300]}")


def run_cmd(
    agent: str | None = typer.Argument(
        None,
        metavar="AGENT",
        help="Agent id to run. Determines the backend and workspace in interactive mode.",
    ),
    prompt: str | None = typer.Option(
        None, "-p", "--prompt",
        help="Prompt text. When given, runs headlessly via the API (POST /api/runs).",
    ),
    headless: bool = typer.Option(
        False, "--headless",
        help="Force headless mode (requires AGENT and --prompt).",
    ),
    backend: str | None = typer.Option(
        None, "-b", "--backend",
        help=(
            "Backend for ad-hoc interactive sessions with no agent "
            "(claude|opencode|codex|pi). Mutually exclusive with --prompt."
        ),
    ),
    workspace: str | None = typer.Option(
        None, "-w", "--workspace",
        help="Named workspace override.",
    ),
    model: str | None = typer.Option(
        None, "-m", "--model",
        help="Model alias override.",
    ),
    ephemeral: bool = typer.Option(
        False, "--ephemeral", "-e",
        help="Force an ephemeral (tmp) workspace.",
    ),
    api: str = typer.Option(
        "http://localhost:8765",
        help="API base URL (headless mode only).",
    ),
    session_id: str | None = typer.Option(
        None, "--session-id",
        help="Session ID to attach to (headless mode only).",
    ),
) -> None:
    """Launch a run — interactive TTY session or headless API call.

    With ``-p/--prompt`` (or ``--headless``): POST the prompt to the API
    and stream events.  Without a prompt flag: exec into the backend's
    native CLI inside the resolved workspace (today's ``ops launch`` behaviour).

    Examples
    --------
    Interactive:
        agentbox run my-agent
        agentbox run --backend claude --workspace research

    Headless:
        agentbox run my-agent -p "Summarise the codebase"
    """
    is_headless = bool(prompt) or headless

    # --- Validation -------------------------------------------------------
    if backend and is_headless:
        console.print(
            "[red]--backend is for interactive sessions only.[/red] "
            "Headless runs require an AGENT id, not a --backend."
        )
        raise typer.Exit(2)

    if is_headless and not agent:
        console.print(
            "[red]Headless mode requires an AGENT id.[/red] "
            "Pass an agent id as the first argument."
        )
        raise typer.Exit(2)

    if is_headless and not prompt:
        console.print(
            "[red]--headless requires a prompt.[/red] "
            "Pass -p/--prompt TEXT."
        )
        raise typer.Exit(2)

    # --- Headless path ----------------------------------------------------
    if is_headless:
        assert agent is not None  # validated above
        assert prompt is not None  # validated above
        body: dict[str, object] = {"agent": agent, "input": prompt}
        if session_id:
            body["session_id"] = session_id
        resp = httpx.post(f"{api}/api/runs", json=body, timeout=30)
        resp.raise_for_status()
        run_id = resp.json()["run_id"]
        console.print(f"[dim]run_id={run_id}[/dim]")
        console.print(
            Panel.fit(
                f"View: [link={api}/runs/{run_id}]{api}/runs/{run_id}[/link]",
                border_style="cyan",
            )
        )
        asyncio.run(_stream(api, run_id))
        return

    # --- Interactive path -------------------------------------------------
    # Determine the runner. Priority: --backend > agent's runner.kind
    runner: str
    if backend:
        runner = backend
    elif agent:
        agent_def = get_store().get_agent_def(agent)
        if agent_def is None:
            console.print(f"[red]Unknown agent:[/red] {agent!r}")
            raise typer.Exit(1)
        raw_kind = agent_def.runner.kind
        runner = _BACKEND_NAME_TO_RUNNER.get(raw_kind, raw_kind)
    else:
        console.print(
            "[red]No agent or --backend specified.[/red] "
            "Pass an AGENT id or --backend {claude|opencode|codex|pi}."
        )
        raise typer.Exit(2)

    sys.exit(
        _launch_session(
            runner=runner,
            agent=agent,
            workspace=workspace,
            model=model,
            ephemeral=ephemeral,
            keep_configs=False,
        )
    )


__all__ = ["run_cmd"]
