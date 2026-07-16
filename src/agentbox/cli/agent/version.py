"""Agent version — ls, show, new, note, publish, rollback."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext, handle_cli_errors, resolve_agent
from agentbox.core.service.agents import AgentNotFound as ServiceAgentNotFound


version_app = typer.Typer(
    name="version",
    help="Inspect and manage agent version history.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# ls
# ---------------------------------------------------------------------------


@version_app.command("ls")
def version_ls(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """List all versions for an agent."""
    obj: CLIContext = ctx.obj
    try:
        obj.agents.require_agent_exists(agent_id)
    except ServiceAgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)

    versions = obj.agents.list_versions(agent_id)
    active = obj.agents.active_version(agent_id)
    latest = obj.agents.latest_version(agent_id)
    if active is None and latest is not None:
        active = latest
    active_id = active["id"] if active else None

    obj.render.agent.versions_table(
        [dict(v) for v in versions],
        agent_id,
        active_id=active_id,
        latest_version=latest["version"] if latest else None,
        active_version=active["version"] if active else None,
    )


# ---------------------------------------------------------------------------
# show  (two args → diff)
# ---------------------------------------------------------------------------


@version_app.command("show")
def version_show(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version_a: int = typer.Argument(
        ..., help="Version number (or first version for diff)"
    ),
    version_b: int | None = typer.Argument(
        None, help="Second version for diff"
    ),
) -> None:
    """Show a version's details, or diff two versions when a second arg is given."""
    obj: CLIContext = ctx.obj
    try:
        obj.agents.require_agent_exists(agent_id)
    except ServiceAgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)

    # Diff path — two version arguments provided
    if version_b is not None:
        with handle_cli_errors():
            result = obj.agents.diff_versions(agent_id, version_a, version_b)
        obj.render.agent.version_diff(result)
        return

    # Single version detail
    v = obj.agents.get_version(agent_id, version_a)
    if v is None:
        obj.render.agent.error(f"version {version_a} not found")
        raise typer.Exit(1)

    version_id = int(v["id"])
    rating = obj.agents.get_rating(version_id)
    comments = obj.agents.list_comments(version_id)

    obj.render.agent.version_detail(
        dict(v),
        rating=dict(rating) if rating else None,
        comments=[dict(c) for c in comments],
    )


# ---------------------------------------------------------------------------
# new  (absorbs: create, prompt-revision, draft)
# ---------------------------------------------------------------------------


@version_app.command("new")
def version_new(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    content_snapshot: str | None = typer.Argument(
        None, help="JSON content snapshot (direct create)"
    ),
    prompt: bool = typer.Option(
        False, "--prompt", help="Create version with new prompt content"
    ),
    prompt_content: str = typer.Option(
        "", "--content", help="New prompt content for --prompt"
    ),
    draft: bool = typer.Option(
        False, "--draft", help="Clone the active version as a new draft"
    ),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
    changelog: str = typer.Option("", "--changelog", help="Changelog"),
    no_activate: bool = typer.Option(
        False, "--no-activate", help="Do not activate the new version"
    ),
) -> None:
    """Create a new agent version.

    Three modes:

    \b
    1. Direct create: provide JSON ``content_snapshot`` (legacy).
       ``agent version new <agent> '{"..."}'``
    2. Prompt revision: ``--prompt --content "new prompt"``.
       ``agent version new <agent> --prompt --content "..."``
    3. Draft clone: ``--draft`` clones the active version.
       ``agent version new <agent> --draft``
    """
    obj: CLIContext = ctx.obj

    if draft:
        # Clone active version as draft
        resolve_agent(agent_id)
        with handle_cli_errors():
            result = obj.agents.branch_draft(agent_id, author=author)
        obj.render.agent.draft_created(
            result.get("version"), result.get("id")
        )
        return

    if prompt:
        # Prompt revision
        try:
            obj.agents.require_agent_exists(agent_id)
        except ServiceAgentNotFound:
            obj.render.agent.error(f"unknown agent {agent_id!r}")
            raise typer.Exit(1)
        with handle_cli_errors():
            result = obj.agents.save_prompt_revision(
                agent_id,
                prompt_content=prompt_content,
                author=author,
                changelog=changelog,
                activate=not no_activate,
            )
        obj.render.agent.prompt_revision_created(
            result["version"], result["id"], not no_activate
        )
        return

    # Direct create from snapshot
    if not content_snapshot:
        obj.render.agent.error(
            "provide a JSON content_snapshot, or use --prompt or --draft"
        )
        raise typer.Exit(2)

    with handle_cli_errors():
        result = obj.agents.create_version_from_snapshot(
            agent_id,
            content_snapshot=content_snapshot,
            author=author,
            changelog=changelog,
        )
    obj.render.agent.version_created(result["version"], result["id"])


# ---------------------------------------------------------------------------
# note  (absorbs: comment + rate)
# ---------------------------------------------------------------------------


@version_app.command("note")
def version_note(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    comment: str | None = typer.Option(
        None, "--comment", help="Comment text to add"
    ),
    stars: int | None = typer.Option(None, "--stars", help="Rating 1-5"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Add a comment and/or star rating to a version."""
    obj: CLIContext = ctx.obj

    if comment is None and stars is None:
        obj.render.agent.error("pass --comment and/or --stars")
        raise typer.Exit(2)

    try:
        obj.agents.require_agent_exists(agent_id)
    except ServiceAgentNotFound:
        obj.render.agent.error(f"unknown agent {agent_id!r}")
        raise typer.Exit(1)

    v = obj.agents.get_version(agent_id, version)
    if v is None:
        obj.render.agent.error(f"version {version} not found")
        raise typer.Exit(1)

    version_id = int(v["id"])

    if comment is not None:
        result = obj.agents.add_comment(version_id, author, comment)
        obj.render.agent.comment_added(result["id"])

    if stars is not None:
        if not 1 <= stars <= 5:
            obj.render.agent.error("rating must be 1-5")
            raise typer.Exit(2)
        with handle_cli_errors():
            obj.agents.set_rating(version_id, stars, author)
        obj.render.agent.version_rated(version, stars)


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


@version_app.command("publish")
def version_publish(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number to publish"),
    reason: str = typer.Option("cli publish", "--reason", help="Publish reason"),
) -> None:
    """Publish a draft version (set as active)."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    with handle_cli_errors():
        result = obj.agents.publish_version(agent_id, version, reason)
    obj.render.agent.version_published(result.get("version"), result.get("id"))


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


@version_app.command("rollback")
def version_rollback(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Target version to roll back to"),
    reason: str = typer.Option(..., "--reason", help="Rollback reason (min 3 chars)"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Roll back to a previous agent version (creates a new version)."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    with handle_cli_errors():
        result = obj.agents.rollback_to(agent_id, version, reason, author=author)
    obj.render.agent.version_rolled_back(version, result.get("version"))