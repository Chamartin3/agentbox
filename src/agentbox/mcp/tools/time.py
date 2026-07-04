"""MCP tool for checking remaining run time."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastmcp import FastMCP

from agentbox.core.data.constants import RunStatus
from agentbox.mcp.context import MCPContext


def register(mcp: FastMCP, ctx: MCPContext) -> None:
    @mcp.tool
    def get_run_time_remaining(run_id: str) -> dict:
        """Return how much time is left for the current run before timeout.

        Use this to decide whether you have enough budget to perform
        additional tool calls, reasoning steps, or output generation.
        """

        run = ctx.execution.get_run(run_id)
        if run is None:
            return {"error": f"run {run_id!r} not found"}

        if not RunStatus(run.status).is_running:
            return {
                "run_id": run_id,
                "status": run.status,
                "remaining_seconds": None,
                "message": f"run is {run.status} — no time budget remaining",
            }

        agent = ctx.agents.get_agent_def(run.agent_id)
        if agent is None:
            return {"error": f"agent {run.agent_id!r} not found"}

        # Prefer the historical runner_snapshot — that's what actually
        # constrained the run. Fall back to agent.runner only for runs
        # that predate the snapshot column.
        timeout: int | None = None
        snap_raw = getattr(run, "runner_snapshot", None)
        if snap_raw:
            try:
                snap = json.loads(snap_raw) if isinstance(snap_raw, str) else snap_raw
                if isinstance(snap, dict):
                    timeout = snap.get("timeout_seconds")
            except (ValueError, TypeError):
                pass
        if timeout is None:
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
