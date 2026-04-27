"""MCP tool for checking remaining run time."""

from __future__ import annotations

from datetime import UTC, datetime

from fastmcp import FastMCP

from agentbox.mcp_server.deps import get_context


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def get_run_time_remaining(run_id: str) -> dict:
        """Return how much time is left for the current run before timeout.

        Use this to decide whether you have enough budget to perform
        additional tool calls, reasoning steps, or output generation.
        """
        store = get_context().store
        loader = get_context().loader

        run = store.get_run(run_id)
        if run is None:
            return {"error": f"run {run_id!r} not found"}

        if run.status != "running":
            return {
                "run_id": run_id,
                "status": run.status,
                "remaining_seconds": None,
                "message": f"run is {run.status} — no time budget remaining",
            }

        agent = loader.get(run.agent_id)
        if agent is None:
            return {"error": f"agent {run.agent_id!r} not found"}

        timeout = agent.runner.timeout_seconds if agent.runner else None
        if timeout is None or timeout <= 0:
            return {
                "run_id": run_id,
                "status": "running",
                "remaining_seconds": None,
                "message": "no timeout configured — unlimited time remaining",
            }

        try:
            start = datetime.fromisoformat(run.created_at)
        except ValueError:
            return {"error": f"invalid created_at timestamp: {run.created_at!r}"}

        elapsed = (datetime.now(UTC) - start).total_seconds()
        remaining = max(0.0, timeout - elapsed)

        if remaining <= 0:
            message = "timeout has elapsed — finish immediately"
        elif remaining < 30:
            message = f"{remaining:.0f}s left — wrap up immediately"
        elif remaining < 120:
            message = f"{remaining:.0f}s left — keep it concise"
        else:
            mins = remaining // 60
            secs = remaining % 60
            message = f"{int(mins)}m {int(secs)}s remaining"

        return {
            "run_id": run_id,
            "status": "running",
            "timeout_seconds": timeout,
            "elapsed_seconds": round(elapsed, 1),
            "remaining_seconds": round(remaining, 1),
            "message": message,
        }
