"""Agent prompts — show, edit, log, save, rollback."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext

from agentbox.core.service import (
    AgentNotFound,
    PromptError,
)

prompt_app = typer.Typer(
    name="prompt",
    help="Manage system prompts: show, edit, log, save, rollback.",
    no_args_is_help=True,
)


@prompt_app.command("show")
def prompt_show(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int | None = typer.Option(
        None, "--version", help="Show a specific version"
    ),
) -> None:
    """Show the active system prompt for an agent (or a specific version)."""
    obj: CLIContext = ctx.obj

    if version is not None:
        committed = obj.agents.get_prompt_version(agent_id, version)
        if committed is None:
            obj.render.agent.error(
                f"version {version} not found for agent {agent_id!r}"
            )
            raise typer.Exit(2)
        content = committed["content"]
    else:
        ver = obj.agents.effective_active_version(agent_id)
        if ver is None:
            obj.render.agent.error(f"unknown agent {agent_id!r}")
            raise typer.Exit(1)
        content = ver.get("prompt_content") or ""

    obj.render.agent.prompt_view(content or "")


@prompt_app.command("edit")
def prompt_edit(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content: str = typer.Argument(..., help="New prompt content"),
) -> None:
    """Write a prompt to disk and create a new committed version."""
    obj: CLIContext = ctx.obj
    try:
        obj.agents.save_prompt_revision(
            agent_id, prompt_content=content, author="cli", changelog="cli edit", activate=True
        )
    except (AgentNotFound, ValueError) as exc:
        if isinstance(exc, AgentNotFound):
            obj.render.agent.error(f"unknown agent {agent_id!r}")
        else:
            obj.render.agent.error(str(exc))
        raise typer.Exit(1)
    obj.render.agent.prompt_updated(agent_id)


@prompt_app.command("log")
def prompt_log(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int | None = typer.Option(
        None, "--version", help="Show a specific version's content"
    ),
) -> None:
    """List prompt versions, or show a specific version with --version."""
    obj: CLIContext = ctx.obj
    try:
        all_versions = obj.agents.list_prompt_versions(agent_id)
    except AgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)

    versions: list[dict[str, object]] = [dict(v) for v in all_versions]

    if version is not None:
        ver = obj.agents.get_prompt_version(agent_id, version)
        if ver is None:
            obj.render.agent.error(f"version {version} not found")
            raise typer.Exit(1)
        obj.render.agent.syntax(str(ver.get("content", "")), "markdown")
        obj.render.agent.dim(
            f"v{ver.get('version', '')} -- {ver.get('author', '')} "
            f"{ver.get('created_at', '')}"
        )
        return

    if not versions:
        obj.render.agent.warn("No prompt versions.")
        return

    obj.render.agent.prompt_versions_table("Versions", versions)


@prompt_app.command("save")
def prompt_save(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content: str = typer.Argument(..., help="Prompt content"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
    changelog: str = typer.Option("", "--changelog", help="Change description"),
) -> None:
    """Save a prompt version (no-op if content unchanged)."""
    obj: CLIContext = ctx.obj
    try:
        obj.agents.save_prompt_version(agent_id, content, author=author, changelog=changelog or "prompt update")
    except AgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)
    obj.render.agent.prompt_updated(agent_id)


@prompt_app.command("rollback")
def prompt_rollback(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    target_version: int = typer.Argument(..., help="Version to roll back to"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Roll back to a previous prompt version."""
    obj: CLIContext = ctx.obj
    try:
        obj.agents.rollback_prompt(agent_id, target_version, author=author)
    except AgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)
    except ValueError as exc:
        obj.render.agent.error(f"rollback failed: {exc}")
        raise typer.Exit(1)
    except PromptError as exc:
        obj.render.agent.error(f"{exc.code}: {exc.detail}")
        raise typer.Exit(1)
    obj.render.agent.prompt_rolled_back(agent_id, target_version)
