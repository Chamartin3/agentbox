"""Agent prompts — show, edit, log, draft, publish, rollback."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CliCtx

# TODO(cli-arch): migrate remaining PromptError handling to AgentService errors
from agentbox.core.service.prompts import (
    AgentNotFound,
    PromptError,
    get_prompt as _get_prompt,
    get_version as _get_version,
    list_versions as _list_versions,
    put_prompt as _put_prompt,
)

prompt_app = typer.Typer(
    name="prompt",
    help="Manage system prompts: show, edit, log, draft, publish, rollback.",
    no_args_is_help=True,
)


@prompt_app.command("show")
def prompt_show(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int | None = typer.Option(
        None, "--version", help="Show a specific committed version"
    ),
) -> None:
    """Show the active system prompt for an agent (or a specific version)."""
    obj: CliCtx = ctx.obj

    if version is not None:
        committed = obj.agents.get_prompt_version(agent_id, version)
        if committed is None:
            obj.render.agent.error(
                f"version {version} not found for agent {agent_id!r}"
            )
            raise typer.Exit(2)
        content = committed["content"]
    else:
        try:
            # TODO(cli-arch): free-fn get_prompt has no AgentService equivalent yet
            doc = _get_prompt(
                agent_id,
                store=obj.store,
                project_root=obj.settings.project_root,
            )
        except AgentNotFound:
            obj.render.agent.error(f"unknown agent {agent_id!r}")
            raise typer.Exit(1)
        except PromptError as exc:
            obj.render.agent.error(f"{exc.code}: {exc.detail}")
            raise typer.Exit(1)
        content = doc.content

    obj.render.agent.prompt_view(content or "")


@prompt_app.command("edit")
def prompt_edit(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content: str = typer.Argument(..., help="New prompt content"),
) -> None:
    """Write a prompt to disk and create a new committed version."""
    obj: CliCtx = ctx.obj
    try:
        # TODO(cli-arch): free-fn put_prompt has no AgentService equivalent yet
        _put_prompt(
            agent_id,
            content,
            store=obj.store,
            project_root=obj.settings.project_root,
        )
    except AgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)
    except PromptError as exc:
        obj.render.agent.error(f"{exc.code}: {exc.detail}")
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
    obj: CliCtx = ctx.obj
    try:
        # TODO(cli-arch): free-fn list_versions has no AgentService equivalent yet
        payload = _list_versions(agent_id, store=obj.store)
    except AgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)

    committed = payload.get("committed", [])
    drafts = payload.get("drafts", [])

    if version is not None:
        # TODO(cli-arch): free-fn get_version has no AgentService equivalent yet
        ver = _get_version(agent_id, version, store=obj.store)
        if ver is None:
            obj.render.agent.error(f"version {version} not found")
            raise typer.Exit(1)
        obj.render.agent.syntax(str(ver.get("content", "")), "markdown")
        obj.render.agent.dim(
            f"v{ver.get('version', '')} -- {ver.get('author', '')} "
            f"{ver.get('created_at', '')}"
        )
        return

    if not committed and not drafts:
        obj.render.agent.warn("No prompt versions.")
        return

    if committed:
        obj.render.agent.prompt_versions_table("Committed", committed)

    if drafts:
        obj.render.agent.prompt_drafts_table(drafts)


@prompt_app.command("draft")
def prompt_draft(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content: str = typer.Argument(..., help="Draft content"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Save a draft prompt (not published until publish is called)."""
    obj: CliCtx = ctx.obj
    try:
        obj.agents.save_prompt_draft(agent_id, content, author=author)
    except AgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)
    obj.render.agent.prompt_draft_saved(agent_id)


@prompt_app.command("publish")
def prompt_publish(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    changelog: str = typer.Option("", "--changelog", help="Publish reason"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Publish the current draft as the active prompt."""
    obj: CliCtx = ctx.obj
    try:
        obj.agents.publish_prompt(agent_id, changelog=changelog, author=author)
    except AgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)
    except ValueError as exc:
        obj.render.agent.error(f"no draft to publish: {exc}")
        raise typer.Exit(1)
    except PromptError as exc:
        obj.render.agent.error(f"{exc.code}: {exc.detail}")
        raise typer.Exit(1)
    obj.render.agent.prompt_published(agent_id)


@prompt_app.command("rollback")
def prompt_rollback(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    target_version: int = typer.Argument(..., help="Version to roll back to"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Roll back to a previous prompt version."""
    obj: CliCtx = ctx.obj
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