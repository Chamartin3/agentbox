"""MCP tools for versioned system-prompt management.

Reads/writes go through the ``agent_versions`` table (DB-as-source-of-truth);
the legacy ``prompt_versions`` table is no longer consulted here. Editing
always creates a new version and requires a non-empty ``reason`` (stored as
the version's changelog). There are no silent updates."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from fastmcp import FastMCP

from agentbox.core.prompt.composition import preview as preview_composition
from agentbox.core.service.agents import resolve_agent
from agentbox.mcp.deps import get_context
from agentbox.mcp.schemas import clamp_limit


def _version_prompt_content(version: dict) -> str:
    """Return the prompt body stored on an ``agent_versions`` row."""
    return (
        version.get("prompt_content")
        or version.get("prompt_snapshot")
        or ""
    )


def _version_meta(version: dict) -> dict:
    """Slim metadata dict for an ``agent_versions`` row."""
    return {
        "version": version.get("version"),
        "version_id": version.get("id"),
        "is_draft": bool(version.get("is_draft", False)),
        "author": version.get("author"),
        "changelog": version.get("changelog"),
        "created_at": version.get("created_at"),
    }


def _resolve_active(store, agent_id: str) -> dict | None:
    """Active version with ``latest_version`` fallback (mirrors the API)."""
    return store.get_active_version(agent_id) or store.latest_version(agent_id)


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def get_prompt(agent_id: str, version: int | None = None) -> dict:
        """Return the published system prompt body for an agent.

        Reads from ``agent_versions.prompt_content`` (DB source of truth).
        When ``version`` is omitted, returns the *active* version (with a
        fallback to the latest row if no active pointer exists). It does
        NOT include composition pieces (references, schemas, user
        template); for those use ``get_agent_prompt_fragments``. For the
        per-run captured fragments, use ``get_run_prompt_fragments``."""
        ctx = get_context()
        agent = resolve_agent(agent_id, store=ctx.store, loader=ctx.loader)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        if version is not None:
            row = ctx.store.get_version(agent_id, version)
            if row is None:
                return {"error": "not_found", "agent_id": agent_id,
                        "version": version}
            return {
                "content": _version_prompt_content(row),
                **_version_meta(row),
            }
        active = _resolve_active(ctx.store, agent_id)
        if active is None:
            return {"error": "no_versions", "agent_id": agent_id}
        return {
            "content": _version_prompt_content(active),
            **_version_meta(active),
        }

    @mcp.tool
    def list_prompt_versions(
        agent_id: str,
        include_drafts: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Paginated history of agent versions for an agent.

        Reads from ``agent_versions``. Each row includes ``is_active`` so
        callers can identify which version is currently pinned."""
        limit = clamp_limit(limit)
        store = get_context().store
        rows = store.list_versions(agent_id)
        if not include_drafts:
            rows = [r for r in rows if not r.get("is_draft")]
        active = store.get_active_version(agent_id)
        active_id = active["id"] if active else None
        total = len(rows)
        page = rows[offset : offset + limit]
        items = [
            {
                **_version_meta(r),
                "is_active": r["id"] == active_id,
                "source": r.get("source"),
            }
            for r in page
        ]
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
            "active_version": active["version"] if active else None,
        }

    @mcp.tool
    def edit_prompt(
        agent_id: str,
        content: str,
        reason: str,
        author: str = "mcp",
    ) -> dict:
        """Edit a system prompt — creates a new active version.

        Writes a new ``agent_versions`` row cloned from the active version
        with ``prompt_content`` replaced, then pins it as active.
        ``reason`` is required (min length 3) and stored as the version's
        changelog."""
        if not reason or len(reason.strip()) < 3:
            return {"error": "reason_required",
                    "detail": "reason must be at least 3 characters"}
        ctx = get_context()
        if resolve_agent(agent_id, store=ctx.store, loader=ctx.loader) is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        try:
            new_row = ctx.store.save_prompt_revision(
                agent_id,
                prompt_content=content,
                author=author,
                changelog=reason.strip(),
                activate=True,
            )
        except ValueError as exc:
            return {"error": "no_active_version", "detail": str(exc)}
        return {
            "content": _version_prompt_content(new_row),
            **_version_meta(new_row),
        }

    @mcp.tool
    def rollback_prompt(
        agent_id: str,
        target_version: int,
        reason: str,
        author: str = "mcp",
    ) -> dict:
        """Rollback to a prior version — creates a NEW active version.

        Calls ``store.rollback_to`` (the same path the UI/API uses), which
        clones ``target_version``'s config + prompt into a new row and
        pins it active."""
        if not reason or len(reason.strip()) < 3:
            return {"error": "reason_required",
                    "detail": "reason must be at least 3 characters"}
        ctx = get_context()
        if resolve_agent(agent_id, store=ctx.store, loader=ctx.loader) is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        try:
            new_row = ctx.store.rollback_to(
                agent_id, target_version, reason.strip(), author=author
            )
        except ValueError as exc:
            return {"error": "rollback_failed", "detail": str(exc)}
        return {
            "content": _version_prompt_content(new_row),
            **_version_meta(new_row),
        }

    @mcp.tool
    def get_prompt_diff(
        agent_id: str, from_version: int, to_version: int
    ) -> dict:
        """Unified diff of ``prompt_content`` between two agent versions."""
        store = get_context().store
        a = store.get_version(agent_id, from_version)
        b = store.get_version(agent_id, to_version)
        if a is None or b is None:
            return {"error": "version_not_found",
                    "from": from_version, "to": to_version}
        diff = difflib.unified_diff(
            _version_prompt_content(a).splitlines(keepends=True),
            _version_prompt_content(b).splitlines(keepends=True),
            fromfile=f"v{from_version}",
            tofile=f"v{to_version}",
        )
        return {"diff": "".join(diff),
                "from_version": from_version, "to_version": to_version}

    @mcp.tool
    def get_agent_prompt_fragments(agent_id: str) -> dict:
        """Return the bundle composition fragments for an agent.

        Shows how the prompt is assembled at the agent level: the raw
        system text, the user_template (if any), each reference file,
        and the input/output JSON schemas. Read-only — no template
        variables are substituted.

        Use this to see the *static* pieces of the prompt before run-time
        injection. For the run-time fragments (user input, MCP config,
        argv, claude_cli envelope), use ``get_run_prompt_fragments``."""
        ctx = get_context()
        agent = resolve_agent(agent_id, store=ctx.store, loader=ctx.loader)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        if agent.source_path is None:
            return {"error": "not_a_bundle", "agent_id": agent_id,
                    "detail": "agent has no bundle source_path"}
        bundle_path = Path(agent.source_path).parent
        if not (bundle_path / "agent.toml").exists():
            return {"error": "not_a_bundle", "agent_id": agent_id,
                    "detail": f"no agent.toml in {bundle_path}"}
        shared_roots: dict[str, Path] = {
            key: ctx.settings.project_root / rel
            for key, rel in (ctx.store.get_project_shared_assets() or {}).items()
        }
        try:
            prev = preview_composition(bundle_path, shared_roots)
        except FileNotFoundError as exc:
            return {"error": "composition_unreadable", "detail": str(exc)}
        return {
            "agent_id": agent_id,
            "bundle_path": str(bundle_path),
            "system": prev.system,
            "user_template": prev.user_template,
            "references": [
                {"path": r.path, "heading": r.heading, "content": r.content}
                for r in prev.references
            ],
            "input_schema": prev.input_schema,
            "output_schema": prev.output_schema,
        }

    @mcp.tool
    def get_run_prompt_fragments(run_id: str) -> dict:
        """Return the per-run captured prompt fragments.

        Each fragment records what was injected into the model for this
        specific run: user input, agent system prompt (post-composition),
        output schema, MCP config, allowed tools, argv, and runner-level
        envelope notes (e.g. Claude CLI's hidden environment block).

        Fragments are tagged with ``source`` (who supplied it) and
        ``injected_by`` (which layer pushed it into model context).
        Inspectable=False means agentbox knows the fragment exists but
        cannot read its bytes (e.g. Claude CLI envelope)."""
        store = get_context().store
        rec = store.get_run(run_id)
        if rec is None:
            return {"error": "not_found", "run_id": run_id}
        raw = store.get_run_prompt(run_id)
        if raw is None:
            return {"run_id": run_id, "fragments": [],
                    "detail": "no fragments captured for this run"}
        try:
            fragments = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"error": "fragments_unreadable", "run_id": run_id,
                    "detail": str(exc)}
        return {"run_id": run_id, "fragments": fragments}
