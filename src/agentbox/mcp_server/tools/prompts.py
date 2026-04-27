"""MCP tools for versioned system-prompt management.

Editing always bumps the version and requires a non-empty ``reason``
(stored as the version's changelog). There are no silent updates."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from fastmcp import FastMCP

from agentbox.core import prompts as prompt_ops
from agentbox.core.composition import preview as preview_composition
from agentbox.mcp_server.deps import get_context
from agentbox.mcp_server.schemas import clamp_limit


def _doc_to_dict(doc) -> dict:
    return {
        "path": doc.path,
        "content": doc.content,
        "size": doc.size,
        "mtime": doc.mtime,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def get_prompt(agent_id: str, version: int | None = None) -> dict:
        """Return the full published system prompt for an agent (single blob).

        This is the versioned ``prompt.md`` content — the system-prompt
        string as committed. It does NOT include composition pieces
        (references, schemas, user template). For those, use
        ``get_agent_prompt_fragments``. For the per-run captured fragments
        (what was actually injected into a specific run), use
        ``get_run_prompt_fragments``."""
        ctx = get_context()
        if version is not None:
            row = ctx.store.get_prompt_version(agent_id, version)
            if row is None:
                return {"error": "not_found", "agent_id": agent_id,
                        "version": version}
            return row
        agent = ctx.loader.get(agent_id)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        doc = prompt_ops.read_versioned(agent, ctx.settings.project_root, ctx.store)
        latest = ctx.store.get_latest_committed_prompt(agent_id)
        return {
            **_doc_to_dict(doc),
            "version": latest["version"] if latest else None,
            "changelog": latest["changelog"] if latest else None,
            "author": latest["author"] if latest else None,
        }

    @mcp.tool
    def list_prompt_versions(
        agent_id: str,
        include_drafts: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Paginated history of prompt versions for an agent."""
        limit = clamp_limit(limit)
        rows = get_context().store.list_prompt_versions(agent_id)
        if not include_drafts:
            rows = [r for r in rows if not r.get("is_draft")]
        total = len(rows)
        page = rows[offset : offset + limit]
        for r in page:
            r.pop("content", None)
        return {
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
        }

    @mcp.tool
    def edit_prompt(
        agent_id: str,
        content: str,
        reason: str,
        author: str = "mcp",
    ) -> dict:
        """Edit a system prompt — bumps version and writes to disk.

        ``reason`` is required (min length 3) and stored as the version's
        changelog. The new version is committed atomically (draft +
        publish in one call). Returns the new committed version."""
        if not reason or len(reason.strip()) < 3:
            return {"error": "reason_required",
                    "detail": "reason must be at least 3 characters"}
        ctx = get_context()
        agent = ctx.loader.get(agent_id)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        ctx.store.save_prompt_draft(agent_id, content, author)
        doc = prompt_ops.publish(
            agent_id,
            ctx.store,
            ctx.settings.project_root,
            agent=agent,
            changelog=reason.strip(),
            author=author,
        )
        latest = ctx.store.get_latest_committed_prompt(agent_id)
        return {
            **_doc_to_dict(doc),
            "version": latest["version"] if latest else None,
            "changelog": latest["changelog"] if latest else None,
            "author": latest["author"] if latest else None,
        }

    @mcp.tool
    def rollback_prompt(
        agent_id: str,
        target_version: int,
        reason: str,
        author: str = "mcp",
    ) -> dict:
        """Rollback to a prior version — creates a NEW version with that content."""
        if not reason or len(reason.strip()) < 3:
            return {"error": "reason_required",
                    "detail": "reason must be at least 3 characters"}
        ctx = get_context()
        agent = ctx.loader.get(agent_id)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        doc = prompt_ops.rollback(
            agent_id,
            ctx.store,
            ctx.settings.project_root,
            target_version,
            agent=agent,
            author=f"{author} (reason: {reason.strip()})",
        )
        latest = ctx.store.get_latest_committed_prompt(agent_id)
        return {
            **_doc_to_dict(doc),
            "version": latest["version"] if latest else None,
            "changelog": latest["changelog"] if latest else None,
        }

    @mcp.tool
    def get_prompt_diff(
        agent_id: str, from_version: int, to_version: int
    ) -> dict:
        """Unified diff between two prompt versions."""
        store = get_context().store
        a = store.get_prompt_version(agent_id, from_version)
        b = store.get_prompt_version(agent_id, to_version)
        if a is None or b is None:
            return {"error": "version_not_found",
                    "from": from_version, "to": to_version}
        diff = difflib.unified_diff(
            a["content"].splitlines(keepends=True),
            b["content"].splitlines(keepends=True),
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
        agent = ctx.loader.get(agent_id)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        if agent.source_path is None:
            return {"error": "not_a_bundle", "agent_id": agent_id,
                    "detail": "agent has no bundle source_path"}
        bundle_path = Path(agent.source_path).parent
        if not (bundle_path / "agent.toml").exists():
            return {"error": "not_a_bundle", "agent_id": agent_id,
                    "detail": f"no agent.toml in {bundle_path}"}
        manifest = ctx.loader.load()
        shared_roots: dict[str, Path] = {
            key: ctx.settings.project_root / rel
            for key, rel in (manifest.shared_assets or {}).items()
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
