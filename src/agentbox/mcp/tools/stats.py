"""MCP tools for usage and activity stats."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.mcp.deps import get_context


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def aggregate_usage() -> dict:
        """Total tokens + cost across all runs."""
        return get_context().store.aggregate_usage()

    @mcp.tool
    def activity_summary(since: str, agent_id: str | None = None) -> dict:
        """Roll up runs since ``since`` (ISO-8601) into totals + breakdowns."""
        return get_context().store.activity_summary(since, agent=agent_id)

    @mcp.tool
    def agent_stats(agent_id: str, since: str) -> dict:
        """Per-agent rollup: run count, success rate, tokens, avg duration."""
        summary = get_context().store.activity_summary(since, agent=agent_id)
        by_action = summary.get("by_action") or []
        agent_row = next(
            (r for r in by_action if r.get("action_name") == agent_id),
            None,
        )
        if agent_row is None:
            return {"agent_id": agent_id, "runs": 0}
        total = agent_row.get("total") or 0
        failures = agent_row.get("failures") or 0
        success_rate = ((total - failures) / total) if total else 0.0
        return {
            "agent_id": agent_id,
            "runs": total,
            "failures": failures,
            "success_rate": success_rate,
            "avg_duration_ms": agent_row.get("avg_duration_ms"),
            "input_tokens": agent_row.get("total_input_tokens"),
            "output_tokens": agent_row.get("total_output_tokens"),
        }

    @mcp.tool
    def list_executors() -> dict:
        """Distinct executor/model names across all recorded runs."""
        items = get_context().store.distinct_executors()
        return {"items": items, "total": len(items)}
