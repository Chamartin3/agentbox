"""agentbox launch — interactive runner for any supported backend.

Launches the bare CLI (no `-p` / `exec --json` / non-interactive flags) inside
a resolved workspace so the user gets a real TTY session. Supports:

- ``claude``    — Claude Code CLI (default)
- ``opencode``  — OpenCode CLI
- ``codex``     — OpenAI Codex CLI
- ``pi``        — pi.dev CLI

The ``token`` (in-process pydantic-ai) backend has no CLI to attach to and
is rejected with a helpful message.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import typer

from agentbox.api.deps import (
    get_loader as _get_loader,  # _NoopLoader stub
)
from agentbox.cli._common import console
from agentbox.config import Settings, load_settings
from agentbox.core.data.manifest import AgentDef
from agentbox.core.run.config import ConfigGenerator
from agentbox.core.workspace.mcp.client import McpRegistry

SUPPORTED_RUNNERS = ("claude", "opencode", "codex", "pi", "shell")
DEFAULT_WORKSPACE_NAME = "default"

# Backends that ship a dedicated CLI. ``shell`` is special-cased: it exec's
# ``$SHELL`` (falling back to /bin/bash) and never needs a runner binary.
_RUNNER_BINARIES = {
    "claude": "claude",
    "opencode": "opencode",
    "codex": "codex",
    "pi": "pi",
}

# Runners that need a generated config bundle (claude_agents.json, MCP
# config, etc.). ``shell`` only generates when ``--keep-configs`` is set,
# so the user can poke at the bundle from inside the shell.
_RUNNERS_NEEDING_CONFIG = {"claude", "opencode"}


def _require_binary(runner: str) -> None:
    """Fail fast if the runner's CLI is not on PATH."""
    binary = _RUNNER_BINARIES.get(runner)
    if binary is None:
        return
    if shutil.which(binary) is None:
        console.print(
            f"[red]The {binary!r} CLI is not installed in this container.[/red]\n"
            f"Add it to [bold]libs/agentbox/Dockerfile[/bold] (or install it "
            f"into the running container) and try again."
        )
        raise typer.Exit(127)


def launch_cmd(
    runner: str = typer.Argument(
        "claude",
        help=f"Runner to launch interactively. One of: {', '.join(SUPPORTED_RUNNERS)}.",
    ),
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Optional agent ID to scope the session to."
    ),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Named workspace (defaults to the 'default' workspace).",
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model alias"),
    ephemeral: bool = typer.Option(
        False, "--ephemeral", "-e", help="Force an ephemeral (tmp) workspace"
    ),
    keep_configs: bool = typer.Option(
        False,
        "--keep-configs/--no-keep-configs",
        help=(
            "Materialize generated runner configs into "
            "<workspace>/.agentbox/generated/ instead of a tmp dir. "
            "Useful for inspecting configs from inside a 'shell' session."
        ),
    ),
) -> None:
    """Launch an interactive backend session inside a workspace.

    Resolves the workspace, applies credentials, generates runner configs
    (for backends that need them), and exec's into the bare CLI.
    """
    sys.exit(
        _launch_session(
            runner=runner,
            agent=agent,
            workspace=workspace,
            model=model,
            ephemeral=ephemeral,
            keep_configs=keep_configs,
        )
    )


def _launch_session(
    *,
    runner: str,
    agent: str | None,
    workspace: str | None,
    model: str | None,
    ephemeral: bool,
    keep_configs: bool,
) -> int:
    """Core launch logic — callable from other CLI commands (e.g. ``ws shell``)."""
    if runner == "token":
        console.print(
            "[red]The 'token' backend runs in-process via pydantic-ai and has "
            "no interactive CLI.[/red]\nUse [bold]agentbox run[/bold] or the HTTP API."
        )
        raise typer.Exit(2)
    if runner not in SUPPORTED_RUNNERS:
        console.print(
            f"[red]Unknown runner:[/red] {runner!r}. "
            f"Expected one of: {', '.join(SUPPORTED_RUNNERS)}."
        )
        raise typer.Exit(2)

    _require_binary(runner)

    settings = load_settings()
    loader = _get_loader()
    manifest = loader.load()

    agent_def: AgentDef | None = None
    if agent:
        from agentbox.api.deps import get_store as _gs

        agent_def = _gs().get_agent_def(agent)
        if agent_def is None:
            console.print(f"[red]Unknown agent:[/red] {agent!r}")
            raise typer.Exit(1)

    workspace_path, is_ephemeral, creds, workspace_name = _resolve_workspace(
        agent_def, workspace, ephemeral, settings, loader
    )

    _apply_creds(creds, settings)

    # Phase 1: sync env-doc, subagents, and resource bindings into the
    # workspace before the runner starts. Skipped for ephemeral/unnamed
    # workspaces (sync_workspace also no-ops on those).
    if workspace_name and not is_ephemeral:
        from agentbox.api.deps import get_store
        from agentbox.core.workspace.sync import sync_workspace

        try:
            sync_result = sync_workspace(
                store=get_store(),
                settings=settings,
                workspace_id=workspace_name,
                workdir=workspace_path,
            )
            if sync_result.errors:
                for err in sync_result.errors:
                    console.print(f"[yellow]sync warning:[/yellow] {err}")
        except Exception as e:
            console.print(f"[yellow]workspace sync failed:[/yellow] {e}")

    # shell mode also needs configs now — we materialize a workspace
    # `.mcp.json` from the resolved per-workspace MCP set so an
    # interactively-launched Claude (run from inside the shell) picks
    # up the workspace-scoped MCP list instead of the global one.
    needs_config = runner in _RUNNERS_NEEDING_CONFIG or runner == "shell"
    gen_dir: Path | None = None
    gen_dir_is_persistent = False
    try:
        if needs_config:
            if keep_configs:
                gen_dir = workspace_path / ".agentbox" / "generated"
                gen_dir.mkdir(parents=True, exist_ok=True)
                gen_dir_is_persistent = True
            else:
                gen_dir = Path(tempfile.mkdtemp(prefix="agentbox-launch-"))
            gen = _make_generator(settings, manifest, workspace_name)
            gen.generate_configs_into(gen_dir)
            # Workspace-local `.mcp.json` for shell mode (and anything
            # else that runs Claude from inside the workspace cwd).
            claude_mcp_src = gen_dir / "claude_mcp.json"
            if claude_mcp_src.is_file():
                shutil.copy(claude_mcp_src, workspace_path / ".mcp.json")

        _print_banner(
            agent, runner, model, workspace_path, is_ephemeral, creds, gen_dir
        )

        if runner == "claude":
            assert gen_dir is not None
            rc = _run_claude(agent, model, workspace_path, gen_dir, agent_def)
        elif runner == "opencode":
            assert gen_dir is not None
            rc = _run_opencode(agent, model, workspace_path, gen_dir)
        elif runner == "codex":
            rc = _run_codex(model, workspace_path)
        elif runner == "pi":
            rc = _run_pi(model, workspace_path)
        elif runner == "shell":
            rc = _run_shell(workspace_path)
        else:  # pragma: no cover — guarded above
            rc = 2
    finally:
        if gen_dir is not None and not gen_dir_is_persistent:
            shutil.rmtree(gen_dir, ignore_errors=True)
        if is_ephemeral:
            shutil.rmtree(workspace_path, ignore_errors=True)

    return rc


# ---------------------------------------------------------------------------
# Workspace + creds resolution
# ---------------------------------------------------------------------------


def _resolve_workspace(
    agent_def: AgentDef | None,
    workspace_override: str | None,
    force_ephemeral: bool,
    settings: Settings,
    loader: object,
) -> tuple[Path, bool, str | None, str | None]:
    """Return (workspace_path, is_ephemeral, creds, workspace_name).

    Resolution order:
      1. ``--ephemeral`` flag → tmp dir.
      2. Explicit ``--workspace`` name (named workspace, then explicit path).
      3. Agent's declared workspace (when ``--agent`` is given).
      4. ``default`` named workspace from the manifest.
      5. Error.

    ``workspace_name`` is the manifest name (used as workspace_id for
    sync). It's ``None`` for ephemeral workspaces and for explicit-path
    overrides that don't correspond to a named workspace.
    """
    if force_ephemeral:
        return Path(tempfile.mkdtemp(prefix="agentbox-ws-")), True, None, None

    ws_name = workspace_override
    if ws_name is None and agent_def is not None:
        ws_name = agent_def.workspace

    if ws_name == "<ephemeral>":
        return Path(tempfile.mkdtemp(prefix="agentbox-ws-")), True, None, None

    if ws_name:
        ws_def = loader.get_workspace(ws_name)
        if ws_def is not None:
            path = settings.project_root / ws_def.path
            path.mkdir(parents=True, exist_ok=True)
            creds = getattr(ws_def, "creds", None)
            return path, False, creds, ws_name
        # Manifest miss — try the DB registry (db-only workspaces created
        # via the API/UI). Returning the name lets sync_workspace
        # materialize env-doc + resource bindings.
        from agentbox.api.deps import get_store

        db_row = get_store().get_workspace(ws_name)
        if db_row is not None:
            rel_path = db_row.get("path")
            path = (
                settings.project_root / rel_path
                if rel_path
                else settings.workspaces_root / ws_name
            )
            path.mkdir(parents=True, exist_ok=True)
            return path, False, None, ws_name
        # Explicit override that isn't a named workspace → treat as relative path
        if workspace_override is not None:
            path = settings.workspaces_root / ws_name
            path.mkdir(parents=True, exist_ok=True)
            return path, False, None, None

    # Fall back to the manifest's "default" workspace
    default_def = loader.get_workspace(DEFAULT_WORKSPACE_NAME)
    if default_def is not None:
        path = settings.project_root / default_def.path
        path.mkdir(parents=True, exist_ok=True)
        creds = getattr(default_def, "creds", None)
        return path, False, creds, DEFAULT_WORKSPACE_NAME

    console.print(
        "[red]No workspace specified and no 'default' workspace defined.[/red]\n"
        "Run [bold]agentbox ws ls[/bold] to see available workspaces, "
        "or pass [bold]--workspace NAME[/bold] / [bold]--ephemeral[/bold]."
    )
    raise typer.Exit(1)


def _apply_creds(creds: str | None, settings: Settings) -> None:
    """Set CLAUDE_CONFIG_DIR or ANTHROPIC_API_KEY based on the creds profile.

    Credential profiles live under ``AGENTBOX_CREDS_DIR`` (default:
    ``/agentbox/creds``). Today only Claude OAuth profiles are wired up;
    other backends pick up whatever is in ``$HOME`` inside the container.
    """
    creds_base = Path(os.environ.get("AGENTBOX_CREDS_DIR", "/agentbox/creds"))
    if not creds or creds == "default":
        os.environ["CLAUDE_CONFIG_DIR"] = str(creds_base / "claude")
    elif creds.startswith("env:"):
        var = creds[4:]
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        api_key = os.environ.get(var)
        if not api_key:
            console.print(f"[red]creds env var {var!r} is not set[/red]")
            raise typer.Exit(1)
        os.environ["ANTHROPIC_API_KEY"] = api_key
    else:
        os.environ["CLAUDE_CONFIG_DIR"] = str(creds_base / f"claude-{creds}")


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def _make_generator(
    settings: Settings,
    manifest: object,
    workspace_id: str | None = None,
) -> ConfigGenerator:
    from agentbox.api.deps import get_store

    mcp_server_name = "mcp"
    mcp_command: list[str] = ["mcp_serve.sh"]
    mcp_url: str | None = None
    mcp_transport: str = "http"
    manifest_specs = list(get_store().get_project_mcp_servers())
    if manifest_specs:
        srv = manifest_specs[0]
        mcp_server_name = srv.name
        mcp_url = srv.url
        mcp_transport = srv.transport
        if srv.command:
            mcp_command = srv.command

    # Per-workspace MCP isolation: resolve overrides and only emit
    # enabled servers. Without a workspace_id we fall back to a single
    # legacy entry (build_claude_mcp_config back-compat path).
    servers: list[dict] | None = None
    if workspace_id and manifest_specs:
        manifest_dicts = [
            {"name": s.name, "config": s.model_dump(exclude={"name"})}
            for s in manifest_specs
        ]
        resolved = get_store().resolve_workspace_mcp(workspace_id, manifest_dicts)
        servers = []
        for entry in resolved.get("servers", []):
            if not entry.get("enabled"):
                continue
            cfg = entry.get("config") or {}
            if not cfg.get("url") and not cfg.get("command"):
                continue
            servers.append(
                {
                    "name": entry["name"],
                    "url": cfg.get("url"),
                    "transport": cfg.get("transport", "http"),
                    "command": cfg.get("command"),
                }
            )

    mcp_registry = McpRegistry(settings.mcp_cache_dir)
    return ConfigGenerator(
        agentbox_toml=settings.manifest_path,
        mcp_manifest=mcp_registry.manifest,
        mcp_server_name=mcp_server_name,
        mcp_command=mcp_command,
        mcp_url=mcp_url,
        mcp_transport=mcp_transport,
        servers=servers,
        verbose=False,
    )


# ---------------------------------------------------------------------------
# Runner launchers
# ---------------------------------------------------------------------------


def _run_claude(
    agent: str | None,
    model: str | None,
    workspace_path: Path,
    gen_dir: Path,
    agent_def: AgentDef | None,
) -> int:
    cmd = ["claude"]
    if model:
        cmd += ["--model", model]
    allowed_tools = (
        agent_def.runner.allowed_tools if agent_def and agent_def.runner else []
    )
    if allowed_tools:
        cmd += ["--allowedTools", *allowed_tools]
    cmd += [
        "--mcp-config",
        str(gen_dir / "claude_mcp.json"),
        "--strict-mcp-config",
        "--settings",
        str(gen_dir / "claude_settings.json"),
    ]
    if agent:
        agents_json = (gen_dir / "claude_agents.json").read_text(encoding="utf-8")
        cmd += ["--agents", agents_json, "--agent", agent]
    result = subprocess.run(cmd, cwd=workspace_path)
    return result.returncode


def _run_opencode(
    agent: str | None,
    model: str | None,
    workspace_path: Path,
    gen_dir: Path,
) -> int:
    oc_config = gen_dir / "opencode.json"
    if oc_config.exists():
        shutil.copy(oc_config, workspace_path / "opencode.json")
    cmd = ["opencode"]
    if agent:
        cmd += ["--agent", agent]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(cmd, cwd=workspace_path)
    return result.returncode


def _run_codex(model: str | None, workspace_path: Path) -> int:
    cmd = ["codex"]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(cmd, cwd=workspace_path)
    return result.returncode


def _run_pi(model: str | None, workspace_path: Path) -> int:
    cmd = ["pi"]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(cmd, cwd=workspace_path)
    return result.returncode


def _run_shell(workspace_path: Path) -> int:
    """Drop into ``$SHELL`` (or bash) inside the workspace."""
    shell = os.environ.get("SHELL", "/bin/bash")
    result = subprocess.run([shell], cwd=workspace_path)
    return result.returncode


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def _print_banner(
    agent: str | None,
    runner: str,
    model: str | None,
    workspace_path: Path,
    is_ephemeral: bool,
    creds: str | None,
    gen_dir: Path | None,
) -> None:
    mode = "ephemeral (tmp)" if is_ephemeral else f"workspace ({workspace_path})"
    console.print("━" * 50)
    label = f"[cyan]{agent}[/cyan]" if agent else "[dim]<no agent>[/dim]"
    console.print(f"[bold]agentbox launch[/bold] ({runner}) — {label}")
    console.print("━" * 50)
    console.print(f"  model:  {model or '<runner default>'}")
    console.print(f"  mode:   {mode}")
    console.print(f"  creds:  {creds or 'default'}")
    if gen_dir is not None:
        console.print(f"  configs:{gen_dir}")
    console.print()
