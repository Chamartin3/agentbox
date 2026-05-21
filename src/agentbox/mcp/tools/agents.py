"""MCP tools for agent discovery."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastmcp import FastMCP

from agentbox.core.service.agents import list_all_agents, resolve_agent
from agentbox.mcp.deps import get_context
from agentbox.mcp.schemas import clamp_limit


def _agent_dict(agent: Any) -> dict:
    if is_dataclass(agent):
        return asdict(agent)
    if hasattr(agent, "model_dump"):
        return agent.model_dump()
    return dict(agent.__dict__)


def _paginate(items: list, limit: int, offset: int) -> dict:
    total = len(items)
    page = items[offset : offset + limit]
    return {
        "items": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < total,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def list_agents(
        tag: str | None = None,
        runner: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Paginated list of agents (DB first, manifest fallback).

        Same source as the REST ``GET /api/agents`` endpoint."""
        limit = clamp_limit(limit)
        ctx = get_context()
        agents = [
            _agent_dict(a) for a in list_all_agents(store=ctx.store, loader=ctx.loader)
        ]
        if tag:
            agents = [a for a in agents if tag in (a.get("tags") or [])]
        if runner:
            agents = [
                a
                for a in agents
                if (a.get("runner") or {}).get("kind") == runner
                or a.get("runner") == runner
            ]
        return _paginate(agents, limit, offset)

    @mcp.tool
    def search_agents(query: str, limit: int = 20, offset: int = 0) -> dict:
        """Substring search across agent id, description, and tags."""
        limit = clamp_limit(limit)
        q = query.lower().strip()
        ctx = get_context()
        results = []
        for a in list_all_agents(store=ctx.store, loader=ctx.loader):
            d = _agent_dict(a)
            hay = " ".join(
                [
                    str(d.get("id") or ""),
                    str(d.get("description") or ""),
                    " ".join(d.get("tags") or []),
                ]
            ).lower()
            if q in hay:
                results.append(d)
        return _paginate(results, limit, offset)

    @mcp.tool
    def get_agent(agent_id: str) -> dict:
        """Full agent definition + active version metadata.

        Reads from ``agent_versions`` / ``active_agent_versions`` (the
        DB-as-source-of-truth tables the UI uses). Falls back to
        ``latest_version`` when no active pointer is set."""
        ctx = get_context()
        agent = resolve_agent(agent_id, store=ctx.store, loader=ctx.loader)
        if agent is None:
            return {"error": "not_found", "agent_id": agent_id}
        active = ctx.store.get_active_version(agent_id) or ctx.store.latest_version(
            agent_id
        )
        prompt_meta = None
        if active:
            prompt_meta = {
                "version": active["version"],
                "version_id": active["id"],
                "is_draft": bool(active.get("is_draft", False)),
                "changelog": active.get("changelog"),
                "author": active.get("author"),
                "created_at": active.get("created_at"),
            }
        return {"agent": _agent_dict(agent), "prompt": prompt_meta}

    @mcp.tool
    def list_agent_tags() -> dict:
        """Distinct tags across all known agents (DB + manifest)."""
        ctx = get_context()
        tags: set[str] = set()
        for a in list_all_agents(store=ctx.store, loader=ctx.loader):
            tags.update(_agent_dict(a).get("tags") or [])
        return {"items": sorted(tags), "total": len(tags)}

    @mcp.tool
    def list_agent_versions(
        agent_id: str,
        include_drafts: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Paginated history of agent_versions rows for an agent.

        Shows version number, draft flag, author, changelog, and whether
        each row is the current active version. Use this to find the
        version number to pass to ``promote_version``.
        """
        limit = clamp_limit(limit)
        ctx = get_context()
        rows = ctx.store.list_versions(agent_id)
        if not include_drafts:
            rows = [r for r in rows if not r.get("is_draft")]
        active = ctx.store.get_active_version(agent_id)
        active_id = active["id"] if active else None
        total = len(rows)
        page = rows[offset : offset + limit]
        items = [
            {
                "version": r["version"],
                "id": r["id"],
                "is_draft": bool(r.get("is_draft")),
                "is_active": r["id"] == active_id,
                "author": r.get("author"),
                "changelog": r.get("changelog"),
                "created_at": r.get("created_at"),
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
    def promote_version(agent_id: str, version: int, reason: str) -> dict:
        """Promote an ``agent_versions`` row to active.

        After this call, new runs for the agent resolve config and prompt
        from the activated row — no process restart needed. Use this to
        publish a draft created by the file-watcher (e.g. a runner/timeout
        change on disk) or to roll forward to a prior committed version.

        ``reason`` (min 3 chars) is recorded so the activation has an
        audit trail in the version's metadata.
        """
        if not reason or len(reason.strip()) < 3:
            return {
                "error": "reason_required",
                "detail": "reason must be at least 3 characters",
            }
        ctx = get_context()
        agent = resolve_agent(agent_id, store=ctx.store, loader=ctx.loader)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        v = ctx.store.get_version(agent_id, version)
        if v is None:
            return {
                "error": "version_not_found",
                "agent_id": agent_id,
                "version": version,
            }
        previous = ctx.store.get_active_version(agent_id)
        ctx.store.activate_version(agent_id, v["id"])
        return {
            "agent_id": agent_id,
            "activated_version": version,
            "version_id": v["id"],
            "is_draft": bool(v.get("is_draft")),
            "previous_active_version": previous["version"] if previous else None,
            "reason": reason.strip(),
        }
