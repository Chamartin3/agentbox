"""agentbox launch — interactive runner for Claude Code and OpenCode agents."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import typer

from agentbox.cli._common import console
from agentbox.config import Settings, load_settings
from agentbox.core.config_generation import ConfigGenerator
from agentbox.core.data.manifest import AgentDef
from agentbox.core.definitions import DefinitionLoader
from agentbox.core.mcp import McpRegistry


def launch_cmd(
    agent: str = typer.Argument(..., help="Agent ID to launch"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Named workspace or path override"
    ),
    runner: str = typer.Option(
        "claude", "--runner", "-r", help="Runner: claude or opencode"
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model alias"),
    ephemeral: bool = typer.Option(
        False, "--ephemeral", "-e", help="Force an ephemeral (tmp) workspace"
    ),
) -> None:
    """Launch an agent interactively inside the container.

    Resolves the workspace, applies credentials, generates runner configs
    from the live manifest, and exec's into the requested runner.
    """
    settings = load_settings()
    loader = DefinitionLoader(settings.project_root)
    manifest = loader.load()

    agent_def = next((a for a in manifest.agents if a.id == agent), None)
    if agent_def is None:
        console.print(f"[red]Unknown agent:[/red] {agent!r}")
        raise typer.Exit(1)

    workspace_path, is_ephemeral, creds = _resolve_workspace(
        agent_def, workspace, ephemeral, settings, loader
    )

    _apply_creds(creds, settings)

    gen_dir = Path(tempfile.mkdtemp(prefix="agentbox-launch-"))
    try:
        gen = _make_generator(settings, manifest)
        gen.generate_configs_into(gen_dir)

        _print_banner(agent, runner, model, workspace_path, is_ephemeral, creds)

        if runner == "opencode":
            rc = _run_opencode(agent, model, workspace_path, gen_dir)
        else:
            rc = _run_claude(agent, model, workspace_path, gen_dir, agent_def)
    finally:
        shutil.rmtree(gen_dir, ignore_errors=True)
        if is_ephemeral:
            shutil.rmtree(workspace_path, ignore_errors=True)

    sys.exit(rc)


# ---------------------------------------------------------------------------
# Workspace + creds resolution
# ---------------------------------------------------------------------------


def _resolve_workspace(
    agent_def: AgentDef,
    workspace_override: str | None,
    force_ephemeral: bool,
    settings: Settings,
    loader: DefinitionLoader,
) -> tuple[Path, bool, str | None]:
    """Return (workspace_path, is_ephemeral, creds)."""
    if force_ephemeral:
        return Path(tempfile.mkdtemp(prefix="agentbox-ws-")), True, None

    ws_name = workspace_override or agent_def.workspace

    if ws_name == "<ephemeral>":
        return Path(tempfile.mkdtemp(prefix="agentbox-ws-")), True, None

    if ws_name:
        ws_def = loader.get_workspace(ws_name)
        if ws_def is not None:
            path = settings.project_root / ws_def.path
            path.mkdir(parents=True, exist_ok=True)
            return path, False, ws_def.creds
        # Not a named workspace — treat as explicit relative path
        path = settings.workspaces_root / ws_name
        path.mkdir(parents=True, exist_ok=True)
        return path, False, None

    path = settings.workspaces_root / agent_def.id
    path.mkdir(parents=True, exist_ok=True)
    return path, False, None


def _apply_creds(creds: str | None, settings: Settings) -> None:
    """Set CLAUDE_CONFIG_DIR or ANTHROPIC_API_KEY based on the creds profile.

    Credential profiles live under ``AGENTBOX_CREDS_DIR`` (default:
    ``/agentbox/creds``), not in ``Settings`` — the dataclass no longer
    carries backend-specific paths.
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


def _make_generator(settings: Settings, manifest: object) -> ConfigGenerator:
    mcp_server_name = "mcp"
    mcp_command: list[str] = ["mcp_serve.sh"]
    mcp_url: str | None = None
    mcp_transport: str = "http"
    if hasattr(manifest, "mcp_servers") and manifest.mcp_servers:
        srv = manifest.mcp_servers[0]
        mcp_server_name = srv.name
        mcp_url = srv.url
        mcp_transport = srv.transport
        if srv.command:
            mcp_command = srv.command
    mcp_registry = McpRegistry(settings.mcp_cache_dir)
    return ConfigGenerator(
        agentbox_toml=settings.manifest_path,
        mcp_manifest=mcp_registry.manifest,
        mcp_server_name=mcp_server_name,
        mcp_command=mcp_command,
        mcp_url=mcp_url,
        mcp_transport=mcp_transport,
        verbose=False,
    )


# ---------------------------------------------------------------------------
# Runner launchers
# ---------------------------------------------------------------------------


def _run_claude(
    agent: str,
    model: str | None,
    workspace_path: Path,
    gen_dir: Path,
    agent_def: AgentDef,
) -> int:
    agents_json = (gen_dir / "claude_agents.json").read_text(encoding="utf-8")
    cmd = ["claude"]
    if model:
        cmd += ["--model", model]
    allowed_tools = (agent_def.runner.allowed_tools if agent_def.runner else [])
    if allowed_tools:
        cmd += ["--allowedTools", *allowed_tools]
    cmd += [
        "--mcp-config", str(gen_dir / "claude_mcp.json"),
        "--strict-mcp-config",
        "--settings", str(gen_dir / "claude_settings.json"),
        "--agents", agents_json,
        "--agent", agent,
    ]
    result = subprocess.run(cmd, cwd=workspace_path)
    return result.returncode


def _run_opencode(
    agent: str,
    model: str | None,
    workspace_path: Path,
    gen_dir: Path,
) -> int:
    oc_config = gen_dir / "opencode.json"
    if oc_config.exists():
        shutil.copy(oc_config, workspace_path / "opencode.json")
    cmd = ["opencode", "--agent", agent]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(cmd, cwd=workspace_path)
    return result.returncode


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def _print_banner(
    agent: str,
    runner: str,
    model: str | None,
    workspace_path: Path,
    is_ephemeral: bool,
    creds: str | None,
) -> None:
    mode = "ephemeral (tmp)" if is_ephemeral else f"workspace ({workspace_path})"
    console.print("━" * 50)
    console.print(f"[bold]CV Agents[/bold] ({runner}) — [cyan]{agent}[/cyan]")
    console.print("━" * 50)
    console.print(f"  model:  {model or '<runner default>'}")
    console.print(f"  mode:   {mode}")
    console.print(f"  creds:  {creds or 'default'}")
    console.print()
