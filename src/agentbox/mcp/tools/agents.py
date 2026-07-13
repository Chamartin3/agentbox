"""MCP tools for agent discovery."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast

from fastmcp import FastMCP

from agentbox.core.data import JsonValue
from agentbox.core.service import EngineService
from agentbox.mcp.context import MCPContext
from agentbox.mcp.schemas import clamp_limit


def _agent_dict(agent: Any) -> dict:
    if is_dataclass(agent) and not isinstance(agent, type):
        return asdict(agent)
    dump = getattr(agent, "model_dump", None)
    if callable(dump):
        return cast(dict, dump())
    return dict(vars(agent))


def _strip_legacy_runner_model(d: dict) -> dict[str, JsonValue]:
    """Drop the legacy ``runner.model`` field from a serialized agent dict.

    The authoritative model lives on the bound runner profile; the
    ``runner.model`` column is cosmetic/import-only and has misled
    operators into thinking it was the runtime value. MCP responses
    surface the profile-resolved model under a top-level ``model`` key
    instead (see ``_inject_profile_model``).
    """
    runner = d.get("runner")
    if isinstance(runner, dict) and "model" in runner:
        runner = {k: v for k, v in runner.items() if k != "model"}
        d["runner"] = runner
    return d


def _inject_profile_model(d: dict, engines: EngineService) -> dict[str, JsonValue]:
    """Resolve the agent's effective model via its bound runner profile.

    Adds ``model``, ``model_provider`` and ``runner_profile_id`` at the
    top level so MCP consumers don't have to make a second call.
    Profile is the single source of truth; falls back to ``None`` when
    no profile is bound (executor will use the system default at run
    time).
    """
    agent_id = d.get("id")
    if not agent_id:
        return d
    try:
        profile = engines.get_agent_runner_profile(agent_id)
    except Exception:
        profile = None
    if profile is not None:
        d["model"] = profile.model
        d["model_provider"] = profile.provider
        d["runner_profile_id"] = profile.id
    else:
        d.setdefault("model", None)
        d.setdefault("model_provider", None)
        d.setdefault("runner_profile_id", None)
    return d


def _paginate(items: list, limit: int, offset: int) -> dict[str, JsonValue]:
    total = len(items)
    page = items[offset : offset + limit]
    return {
        "items": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < total,
    }


def register(mcp: FastMCP, ctx: MCPContext) -> None:
    @mcp.tool
    def list_agents(
        tag: str | None = None,
        runner: str | None = None,
        limit: int = 20,
        offset: int = 0,
        include_disabled: bool = False,
    ) -> dict:
        """Paginated list of agents (DB first, manifest fallback).

        Same source as the REST ``GET /api/agents`` endpoint. Pass
        ``include_disabled=True`` to surface disabled agents (each
        carries a ``disabled_at`` timestamp; invoking one would fail
        with ``agent_disabled``)."""
        limit = clamp_limit(limit)
        svc = ctx.agents

        def _attach_disabled(d: dict) -> dict:
            agent_id = d.get("id")
            meta = svc.get_meta(agent_id) if agent_id else None
            d["disabled_at"] = (meta or {}).get("disabled_at")
            return d

        agents = [
            _attach_disabled(
                _inject_profile_model(
                    _strip_legacy_runner_model(_agent_dict(a)),
                    ctx.engines,
                )
            )
            for a in svc.list_all_agents(include_disabled=include_disabled)
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
        results = []
        for a in ctx.agents.list_all_agents():
            d = _agent_dict(a)
            hay = " ".join(
                [
                    str(d.get("id") or ""),
                    str(d.get("description") or ""),
                    " ".join(d.get("tags") or []),
                ]
            ).lower()
            if q in hay:
                results.append(
                    _inject_profile_model(_strip_legacy_runner_model(d), ctx.engines)
                )
        return _paginate(results, limit, offset)

    @mcp.tool
    def get_agent(agent_id: str) -> dict:
        """Full agent definition + active version metadata.

        Reads from ``agent_versions`` / ``active_agent_versions`` (the
        DB-as-source-of-truth tables the UI uses). Falls back to
        ``latest_version`` when no active pointer is set."""
        svc = ctx.agents
        agent = svc.resolve_agent(agent_id)
        if agent is None:
            return {"error": "not_found", "agent_id": agent_id}
        active = svc.active_version(agent_id) or svc.latest_version(agent_id)
        prompt_meta = None
        if active:
            prompt_meta = {
                "version": active["version"],
                "version_id": active["id"],
                "changelog": active.get("changelog"),
                "author": active.get("author"),
                "created_at": active.get("created_at"),
            }
        agent_payload = _inject_profile_model(
            _strip_legacy_runner_model(_agent_dict(agent)), ctx.engines
        )
        meta = svc.get_meta(agent_id) or {}
        agent_payload["disabled_at"] = meta.get("disabled_at")
        return {"agent": agent_payload, "prompt": prompt_meta}

    @mcp.tool
    def list_agent_tags() -> dict:
        """Distinct tags across all known agents (DB + manifest)."""
        tags: set[str] = set()
        for a in ctx.agents.list_all_agents():
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

        Shows version number, author, changelog, and whether each row is
        the current active version. Use this to find the version number to
        pass to ``promote_version``.
        """
        limit = clamp_limit(limit)
        svc = ctx.agents
        rows = svc.list_versions(agent_id)
        # ``include_drafts`` is retained for API compatibility but ignored —
        # the draft concept was removed from agent_versions.
        del include_drafts
        active = svc.active_version(agent_id)
        active_id = active["id"] if active else None
        total = len(rows)
        page = rows[offset : offset + limit]
        items = [
            {
                "version": r["version"],
                "id": r["id"],
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
        svc = ctx.agents
        agent = svc.resolve_agent(agent_id)
        if agent is None:
            return {"error": "agent_not_found", "agent_id": agent_id}
        v = svc.get_version(agent_id, version)
        if v is None:
            return {
                "error": "version_not_found",
                "agent_id": agent_id,
                "version": version,
            }
        previous = svc.active_version(agent_id)
        svc.activate_version(agent_id, v["id"])
        return {
            "agent_id": agent_id,
            "activated_version": version,
            "version_id": v["id"],
            "previous_active_version": previous["version"] if previous else None,
            "reason": reason.strip(),
        }
