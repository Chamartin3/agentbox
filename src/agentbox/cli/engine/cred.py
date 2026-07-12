"""Unified credential bootstrap — ``agentbox engine cred``."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import typer

from agentbox.core.data.payload_types import CredentialContext
from agentbox.cli.shared import CLIContext, EngineRenderer  # TODO(cli-arch): transitional renderer import — plan 095
from agentbox.core.config import Settings
from agentbox.core.service.engines import CredentialMethod, CredentialState, Method
from agentbox.core.service.engines import EngineService

creds_app = typer.Typer(
    name="creds",
    help="Credential management: setup, status, import, clear.",
    no_args_is_help=True,
)


@creds_app.command()
def setup(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="Backend name to set up (e.g. claude, opencode, openai). Omit for interactive walkthrough.",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        help="Try every registered backend, skip none.",
    ),
) -> None:
    """Interactive credential setup walkthrough."""
    obj: CLIContext = ctx.obj
    engines = obj.engines
    render = obj.render.engine
    settings = obj.settings
    all_items = engines.list_credentials()
    if not all_items:
        render.credential_no_backends_registered()
        return
    if name:
        cm = engines.get_credential(name)
        if cm is None:
            render.credential_unknown_backend(name)
            raise typer.Exit(1)
        _setup_one(cm, engines, render, settings, skip_choice=all)
        return
    if all:
        for cm in all_items:
            _setup_one(cm, engines, render, settings, skip_choice=True)
        return
    _interactive_setup(all_items, engines, render, settings)


def _interactive_setup(
    items: list[CredentialMethod],
    engines: EngineService,
    render: EngineRenderer,
    settings: Settings,
) -> None:
    render.credential_setup_header()
    for cm in items:
        _setup_one_interactive(cm, engines, render, settings)


def _setup_one_interactive(
    cm: CredentialMethod,
    engines: EngineService,
    render: EngineRenderer,
    settings: Settings,
) -> None:
    state = cm.detect()
    state_icon = render._state_name_to_style(state)
    render.print(f"\n[{state_icon}]{cm.label}[/{state_icon}] ({cm.backend})")
    if state == CredentialState.PRESENT:
        render.credential_skip_detected()
        return
    methods = cm.methods
    if not methods:
        render.credential_no_methods()
        return
    render.print("  Choose method:")
    for i, m in enumerate(methods):
        render.print(f"    {i + 1}) {m.label}")
    choice = typer.prompt("  >", default="s", show_default=False)
    if choice.lower() in ("s", "skip", ""):
        render.credential_skipped()
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(methods):
            _apply_method(cm, methods[idx], render, settings)
        else:
            render.credential_invalid_choice()
    except ValueError:
        render.credential_invalid_input()


def _setup_one(
    cm: CredentialMethod,
    engines: EngineService,
    render: EngineRenderer,
    settings: Settings,
    skip_choice: bool = False,
) -> None:
    state = cm.detect()
    state_icon = render._state_name_to_style(state)
    render.print(f"[{state_icon}]{cm.label}[/{state_icon}] ({cm.backend})")
    if state == CredentialState.PRESENT:
        render.credential_already_configured()
        return
    methods = cm.methods
    if not methods:
        render.credential_no_methods()
        return
    if skip_choice:
        _apply_method(cm, methods[0], render, settings)
        return
    if len(methods) == 1:
        _apply_method(cm, methods[0], render, settings)
    else:
        render.credential_multiple_methods_hint()


def _apply_method(
    cm: CredentialMethod,
    method: Method,
    render: EngineRenderer,
    settings: Settings,
) -> None:
    ctx: CredentialContext = {
        "creds_base": str(settings.creds_dir),
        "env_file": str(settings.creds_env_file),
    }
    try:
        method.apply(ctx)
        new_state = cm.detect()
        if new_state == CredentialState.PRESENT:
            render.credential_configured(method.label)
        else:
            render.credential_method_warning()
    except Exception as exc:
        render.credential_method_failed(exc)


@creds_app.command()
def status(
    ctx: typer.Context,
    probe: bool = typer.Option(
        False, "--probe", help="Probe credentials with a lightweight API call."
    ),
) -> None:
    """Show credential status for every registered backend."""
    obj: CLIContext = ctx.obj
    all_items = obj.engines.list_credentials()
    obj.render.engine.credential_status_table(all_items)


@creds_app.command(name="import")
def import_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Backend name to import credentials for (e.g. claude)."),
) -> None:
    """Non-interactive host credential import for a backend."""
    obj: CLIContext = ctx.obj
    render = obj.render.engine
    cm = obj.engines.get_credential(name)
    if cm is None:
        render.credential_unknown_backend(name)
        raise typer.Exit(1)
    for m in cm.methods:
        if m.key == "import_host":
            _apply_method(cm, m, render, obj.settings)
            return
    render.credential_no_import_method(name)
    raise typer.Exit(1)


@creds_app.command(name="clear")
def clear_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Backend name to clear credentials for."),
) -> None:
    """Remove stored credentials for one backend."""
    obj: CLIContext = ctx.obj
    render = obj.render.engine
    settings = obj.settings
    cm = obj.engines.get_credential(name)
    if cm is None:
        render.credential_unknown_backend(name)
        raise typer.Exit(1)
    cleared = False
    oauth_dir = settings.creds_dir / name
    if oauth_dir.exists():
        shutil.rmtree(oauth_dir)
        render.credential_dir_removed(str(oauth_dir))
        cleared = True
    for child in settings.creds_dir.iterdir():
        if child.is_dir() and child.name.startswith(f"{name}-"):
            shutil.rmtree(child)
            render.credential_dir_removed(str(child))
            cleared = True
    if settings.creds_env_file.exists():
        env_vars = [m.env_var for m in cm.methods if m.env_var]
        if env_vars:
            _remove_env_lines(settings.creds_env_file, env_vars)
            render.credential_env_removed(str(settings.creds_env_file))
            cleared = True
    if not cleared:
        render.credential_none_found(name)
    else:
        render.credential_cleared()


def _remove_env_lines(env_path: Path, keys: list[str]) -> None:
    if not env_path.exists():
        return
    key_set = set(keys)
    lines = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)\s*=", line)
        if m and m.group(1) in key_set:
            continue
        lines.append(line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
