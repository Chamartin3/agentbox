"""Launch helpers — shared session logic for interactive backend sessions.

Provides ``_launch_session`` (the core launch logic), workspace/creds
resolution, MCP config generation, and per-runner launchers. These are
shared by ``agentbox run`` (interactive mode) and ``agentbox ops shell``.

Supports: claude, opencode, codex, pi. The ``token`` backend has no
interactive CLI and is rejected with a helpful message.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import typer

from agentbox.cli.shared import CLIContext
from agentbox.cli.shared.renderers.ops import OpsRenderer
from agentbox.core.config import Settings  # TODO(cli-arch): Settings (plan 095)
from agentbox.core.data.constants import RunnerKind  # TODO(cli-arch): RunnerKind export (plan 095)
from agentbox.core.service import AgentDef, WorkspaceService  # TODO(cli-arch): facade export (plan 095)
# TODO(cli-arch): launch/shell orchestration → Workspace/Execution Service (plans 089/095)
from agentbox.core.service.system import SystemService
# TODO(cli-arch): launch/shell orchestration → Workspace/Execution Service (plans 089/095)
from agentbox.core.workspaces.tooling.mcp import McpRegistry

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
_RUNNERS_NEEDING_CONFIG = {RunnerKind.CLAUDE, RunnerKind.OPENCODE}


def _require_binary(runner: str, ops: OpsRenderer) -> None:
    """Fail fast if the runner's CLI is not on PATH."""
    binary = _RUNNER_BINARIES.get(runner)
    if binary is None:
        return
    if shutil.which(binary) is None:
        ops.error(
            f"The {binary!r} CLI is not installed in this container.\n"
            f"Add it to libs/agentbox/Dockerfile (or install it "
            f"into the running container) and try again."
        )
        raise typer.Exit(127)


def _launch_session(
    obj: CLIContext,
    *,
    runner: str,
    agent: str | None,
    workspace: str | None,
    model: str | None,
    ephemeral: bool,
    keep_configs: bool,
) -> int:
    """Core launch logic — callable from other CLI commands (e.g. ``ws shell``)."""
    ops = obj.render.ops
    settings = obj.settings

    if runner == "token":
        ops.error(
            "The 'token' backend runs in-process via pydantic-ai and has "
            "no interactive CLI.\nUse agentbox run or the HTTP API."
        )
        raise typer.Exit(2)
    try:
        RunnerKind.coerce(runner, label="runner")
    except ValueError:
        ops.error(
            f"Unknown runner: {runner!r}. "
            f"Expected one of: {', '.join(RunnerKind.values())}."
        )
        raise typer.Exit(2)

    _require_binary(runner, ops)

    agent_def: AgentDef | None = None
    if agent:
        agent_def = obj.agents.resolve_agent(agent)
        if agent_def is None:
            ops.error(f"Unknown agent: {agent!r}")
            raise typer.Exit(1)

    workspace_path, is_ephemeral, creds, workspace_name = _resolve_workspace(
        agent_def, workspace, ephemeral, settings, ops, obj.workspaces
    )

    _apply_creds(creds, settings, ops)

    # Sync env-doc, subagents, and resource bindings into the
    # workspace before the runner starts. Skipped for ephemeral/unnamed
    # workspaces (build_workspace also no-ops on those).
    if workspace_name and not is_ephemeral:
        try:
            sync_result = obj.workspaces.build_workspace(workspace_name)
            if sync_result and sync_result.errors:
                for err in sync_result.errors:
                    ops.warn(f"sync warning: {err}")
        except Exception as e:
            ops.warn(f"workspace sync failed: {e}")

    # shell mode also needs configs now — we materialize a workspace
    # `.mcp.json` from the resolved per-workspace MCP set so an
    # interactively-launched Claude (run from inside the shell) picks
    # up the workspace-scoped MCP list instead of the global one.
    needs_config = runner in _RUNNERS_NEEDING_CONFIG or runner == RunnerKind.SHELL
    config_cm: contextlib.AbstractContextManager = contextlib.nullcontext()
    if needs_config:
        _registry, servers = _resolve_mcp_for_launch(
            settings, workspace_name, obj.system, obj.workspaces
        )
        # The service owns placing native runner config in the workspace
        # cwd (where the engine discovers it) and cleaning up what it wrote.
        config_cm = obj.workspaces.launch_runner_configs(
            workspace_path,
            servers=servers,
            keep=keep_configs,
        )
    try:
        with config_cm:
            ops.launch_banner(agent, runner, model, workspace_path, is_ephemeral, creds)
            if runner == RunnerKind.CLAUDE:
                rc = _run_claude(agent, model, workspace_path, agent_def)
            elif runner == RunnerKind.OPENCODE:
                rc = _run_opencode(agent, model, workspace_path)
            elif runner == RunnerKind.CODEX:
                rc = _run_codex(model, workspace_path)
            elif runner == RunnerKind.PI:
                rc = _run_pi(model, workspace_path)
            elif runner == RunnerKind.SHELL:
                rc = _run_shell(workspace_path)
            else:  # pragma: no cover — guarded above
                rc = 2
    finally:
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
    ops: OpsRenderer,
    workspace_svc: WorkspaceService,
) -> tuple[Path, bool, str | None, str | None]:
    """Return (workspace_path, is_ephemeral, creds, workspace_name).

    Resolution order:
      1. ``--ephemeral`` flag → tmp dir.
      2. Explicit ``--workspace`` name (DB registry, then explicit path).
      3. Agent's declared workspace (when ``--agent`` is given).
      4. Error.

    ``workspace_name`` is the registry name (used as workspace_id for
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
        # Look up the DB registry (workspaces created via the API/UI).
        # Returning the name lets build_workspace materialize env-doc +
        # resource bindings.
        db_row = workspace_svc.get_workspace(ws_name)
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

    ops.error(
        "No workspace specified and no 'default' workspace defined.\n"
        "Run agentbox ws ls to see available workspaces, "
        "or pass --workspace NAME / --ephemeral."
    )
    raise typer.Exit(1)


def _apply_creds(creds: str | None, settings: Settings, ops: OpsRenderer) -> None:
    """Set CLAUDE_CONFIG_DIR or ANTHROPIC_API_KEY based on the creds profile.

    Credential profiles live under ``SETTINGS.creds_dir``. Today only
    Claude OAuth profiles are wired up; other backends pick up whatever
    is in ``$HOME`` inside the container.
    """
    creds_base = settings.creds_dir
    if not creds or creds == "default":
        os.environ["CLAUDE_CONFIG_DIR"] = str(creds_base / "claude")
    elif creds.startswith("env:"):
        var = creds[4:]
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        api_key = os.environ.get(var)
        if not api_key:
            ops.error(f"creds env var {var!r} is not set")
            raise typer.Exit(1)
        os.environ["ANTHROPIC_API_KEY"] = api_key
    else:
        os.environ["CLAUDE_CONFIG_DIR"] = str(creds_base / f"claude-{creds}")


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def _resolve_mcp_for_launch(
    settings: Settings,
    workspace_id: str | None,
    system_svc: SystemService,
    workspace_svc: WorkspaceService,
) -> tuple[McpRegistry, list[dict] | None]:
    """Resolve MCP registry and workspace-specific server overrides.

    Returns ``(mcp_registry, servers)`` where *servers* is the
    workspace-filtered MCP server list (or None when there's no
    workspace_id).
    """
    manifest_specs = list(system_svc.get_project_mcp_servers())

    # Per-workspace MCP isolation: resolve overrides and only emit
    # enabled servers. Without a workspace_id we fall back to the
    # global server list (handled by make_generator).
    servers: list[dict] | None = None
    if workspace_id and manifest_specs:
        manifest_dicts = [
            {"name": s.name, "config": s.model_dump(exclude={"name"})}
            for s in manifest_specs
        ]
        resolved = workspace_svc.resolve_workspace_mcp(workspace_id, manifest_dicts)
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
    return mcp_registry, servers


# ---------------------------------------------------------------------------
# Runner launchers
# ---------------------------------------------------------------------------


def _run_claude(
    agent: str | None,
    model: str | None,
    workspace_path: Path,
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
    # Native config lives in the cwd: .mcp.json + .claude/agents/*.md.
    cmd += ["--mcp-config", ".mcp.json", "--strict-mcp-config"]
    if agent:
        cmd += ["--agent", agent]
    result = subprocess.run(cmd, cwd=workspace_path)
    return result.returncode


def _run_opencode(
    agent: str | None,
    model: str | None,
    workspace_path: Path,
) -> int:
    # opencode.json is rendered into the cwd by launch_runner_configs.
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



