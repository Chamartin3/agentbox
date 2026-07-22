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

from agentbox.cli.ops.launch import launch_session
from agentbox.cli.shared import CLIContext
from agentbox.cli.shared.context import Renderers
from agentbox.core.data.constants import BackendName

# Mapping from BackendName values to RunnerKind strings used by launch_session.
# "token" passes through and is rejected by launch_session with a clear message.


async def _stream(renderers: Renderers, api: str, run_id: str) -> None:
    ws_url = api.replace("http", "ws") + f"/api/runs/{run_id}/stream"
    async with websockets.connect(ws_url) as ws:
        async for msg in ws:
            ev = json.loads(msg)
            t = ev.get("type", "?")
            renderers.run.event_line(t, ev)


def _resolve_obj(ctx: typer.Context) -> CLIContext:
    """Resolve CLIContext from typer context, falling back to build_ctx()."""
    if isinstance(ctx.obj, CLIContext):
        return ctx.obj
    from agentbox.cli.shared.context import build_ctx  # noqa: PLC0415
    return build_ctx()


def run_cmd(
    ctx: typer.Context,
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
    obj = _resolve_obj(ctx)
    renders = obj.render

    is_headless = bool(prompt) or headless

    # --- Validation -------------------------------------------------------
    if backend and is_headless:
        renders.ops.error(
            "--backend is for interactive sessions only. "
            "Headless runs require an AGENT id, not a --backend."
        )
        raise typer.Exit(2)

    if is_headless and not agent:
        renders.ops.error(
            "Headless mode requires an AGENT id. "
            "Pass an agent id as the first argument."
        )
        raise typer.Exit(2)

    if is_headless and not prompt:
        renders.ops.error(
            "--headless requires a prompt. Pass -p/--prompt TEXT."
        )
        raise typer.Exit(2)

    # --- Headless path ----------------------------------------------------
    if is_headless:
        assert agent is not None  # validated above
        assert prompt is not None  # validated above
        body: dict[str, object] = {"agent": agent, "input": prompt}
        if session_id:
            body["session_id"] = session_id
        if ephemeral:
            body["fresh_workspace"] = True
        resp = httpx.post(f"{api}/api/runs", json=body, timeout=30)
        resp.raise_for_status()
        run_id = resp.json()["run_id"]
        renders.ops.dim(f"run_id={run_id}")
        renders.ops.panel(
            f"View: [link={api}/runs/{run_id}]{api}/runs/{run_id}[/link]",
            title="run",
            border="cyan",
        )
        asyncio.run(_stream(renders, api, run_id))
        return

    # --- Interactive path -------------------------------------------------
    # Determine the runner. Priority: --backend > the agent's effective backend
    # (resolved from its runner profile / settings default — never runner.kind).
    runner: str
    if backend:
        runner = backend
    elif agent:
        agent_def = obj.agents.get_agent_def(agent)
        if agent_def is None:
            renders.ops.error(f"Unknown agent: {agent!r}")
            raise typer.Exit(1)
        runner = BackendName.runner_for(obj.engines.effective_backend(agent_def))
    else:
        renders.ops.error(
            "No agent or --backend specified. "
            "Pass an AGENT id or --backend {claude|opencode|codex|pi}."
        )
        raise typer.Exit(2)

    sys.exit(
        launch_session(
            obj=obj,
            runner=runner,
            agent=agent,
            workspace=workspace,
            model=model,
            ephemeral=ephemeral,
            keep_configs=False,
        )
    )


__all__ = ["run_cmd"]
