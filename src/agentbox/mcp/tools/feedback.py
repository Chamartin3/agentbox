"""MCP tools for usage, activity stats, comments, and ratings."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.mcp.context import MCPContext


def _success_rate(total: int, failures: int) -> float:
    return ((total - failures) / total) if total else 0.0


def register(mcp: FastMCP, ctx: MCPContext) -> None:
    @mcp.tool
    def aggregate_usage() -> dict:
        """Total tokens + cost across all runs."""
        return ctx.evaluation.aggregate_usage()

    @mcp.tool
    def activity_summary(since: str, agent_id: str | None = None) -> dict:
        """Roll up runs since ``since`` (ISO-8601) into totals + breakdowns."""
        return ctx.evaluation.activity_summary(since, agent=agent_id)

    @mcp.tool
    def agent_stats(agent_id: str, since: str) -> dict:
        """Per-agent rollup: run count, success rate, tokens, avg duration."""
        summary = ctx.evaluation.activity_summary(since, agent=agent_id)
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
            "success_rate": _success_rate(total, failures),
            "avg_duration_ms": agent_row.get("avg_duration_ms"),
            "input_tokens": agent_row.get("total_input_tokens"),
            "output_tokens": agent_row.get("total_output_tokens"),
        }

    @mcp.tool
    def list_executors() -> dict:
        """Distinct executor/model names across all recorded runs."""
        items = ctx.evaluation.distinct_executors()
        return {"items": items, "total": len(items)}

    @mcp.tool
    def list_run_comments(run_id: str) -> dict:
        """List human/agent comments attached to a run."""
        if ctx.execution.get_run(run_id) is None:
            return {"error": "not_found", "run_id": run_id}
        return {"run_id": run_id, "comments": ctx.execution.list_run_comments(run_id)}

    @mcp.tool
    def add_run_comment(run_id: str, body: str, author: str = "mcp") -> dict:
        """Append a review comment to a run.

        ``body`` is required and must be non-empty. ``author`` defaults to
        ``"mcp"`` — pass an agent name so provenance is preserved.
        """
        if not body or not body.strip():
            return {"error": "empty_body"}
        if ctx.execution.get_run(run_id) is None:
            return {"error": "not_found", "run_id": run_id}
        try:
            row = ctx.execution.add_run_comment(run_id, author, body)
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
        try:
            ctx.agents.set_rating(version_id, rating, rater=rater)
            return {"version_id": version_id, "rating": rating, "rater": rater}
        except Exception as exc:
            return {"error": str(exc), "version_id": version_id}

    @mcp.tool
    def list_agent_version_ratings(version_id: int) -> dict:
        """Return ratings + comments for an agent version."""
        rating = ctx.agents.get_rating(version_id)
        comments = ctx.agents.list_comments(version_id)
        return {
            "version_id": version_id,
            "rating": rating,
            "comments": comments,
        }
