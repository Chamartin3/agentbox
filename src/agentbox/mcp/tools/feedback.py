"""MCP tools for usage, activity stats, comments, and ratings."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.core.service.execution.feedback import (
    activity_summary as svc_activity_summary,
    add_comment as _add_run_comment,
    aggregate_usage as svc_aggregate_usage,
    distinct_executors as svc_distinct_executors,
    list_comments as _list_run_comments,
    success_rate,
)
from agentbox.mcp.deps import get_context


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def aggregate_usage() -> dict:
        """Total tokens + cost across all runs."""
        return svc_aggregate_usage(store=get_context().store)

    @mcp.tool
    def activity_summary(since: str, agent_id: str | None = None) -> dict:
        """Roll up runs since ``since`` (ISO-8601) into totals + breakdowns."""
        return svc_activity_summary(
            since=since, agent_id=agent_id, store=get_context().store
        )

    @mcp.tool
    def agent_stats(agent_id: str, since: str) -> dict:
        """Per-agent rollup: run count, success rate, tokens, avg duration."""
        summary = svc_activity_summary(
            since=since, agent_id=agent_id, store=get_context().store
        )
        by_action = summary.get("by_action") or []
        agent_row = next(
            (r for r in by_action if r.get("action_name") == agent_id),
            None,
        )
        if agent_row is None:
            return {"agent_id": agent_id, "runs": 0}
        total = agent_row.get("total") or 0
        failures = agent_row.get("failures") or 0
        return {
            "agent_id": agent_id,
            "runs": total,
            "failures": failures,
            "success_rate": success_rate(total, failures),
            "avg_duration_ms": agent_row.get("avg_duration_ms"),
            "input_tokens": agent_row.get("total_input_tokens"),
            "output_tokens": agent_row.get("total_output_tokens"),
        }

    @mcp.tool
    def list_executors() -> dict:
        """Distinct executor/model names across all recorded runs."""
        items = svc_distinct_executors(store=get_context().store)
        return {"items": items, "total": len(items)}

    @mcp.tool
    def list_run_comments(run_id: str) -> dict:
        """List human/agent comments attached to a run."""
        store = get_context().store
        return _list_run_comments(run_id, store=store)

    @mcp.tool
    def add_run_comment(run_id: str, body: str, author: str = "mcp") -> dict:
        """Append a review comment to a run.

        ``body`` is required and must be non-empty. ``author`` defaults to
        ``"mcp"`` — pass an agent name so provenance is preserved.
        """
        if not body or not body.strip():
            return {"error": "empty_body"}
        store = get_context().store
        try:
            row = _add_run_comment(run_id, store=store, author=author, body=body)
            return {"run_id": run_id, "comment": row}
        except Exception as exc:
            return {"error": str(exc), "run_id": run_id}

    @mcp.tool
    def add_agent_version_rating(
        version_id: int, rating: int, reason: str = "", rater: str = "mcp"
    ) -> dict:
        """Rate an agent version (1–5)."""
        if not 1 <= rating <= 5:
            return {"error": "rating must be 1–5"}
        store = get_context().store
        try:
            store.set_rating(version_id, rating, rater=rater)
            return {"version_id": version_id, "rating": rating, "rater": rater}
        except Exception as exc:
            return {"error": str(exc), "version_id": version_id}

    @mcp.tool
    def list_agent_version_ratings(version_id: int) -> dict:
        """Return ratings + comments for an agent version."""
        store = get_context().store
        rating = store.get_rating(version_id)
        comments = store.list_comments(version_id)
        return {
            "version_id": version_id,
            "rating": rating,
            "comments": comments,
        }
