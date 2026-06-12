"""Shared models used by both profiles.py and stats.py — no intra-package imports."""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from agentbox.core.data.engines.profiles import RunnerProfile


class RunnerProfileStats(BaseModel):
    """Statistics for a runner profile."""

    profile_id: str
    runs: int
    succeeded: int
    failed: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None
    avg_duration_ms: float | None = None
    last_run_at: str | None = None


def _row_to_profile(row) -> RunnerProfile:
    """Convert a database row to a RunnerProfile model."""
    from agentbox.core.data.engines.profiles import RunnerProfile  # noqa: PLC0415

    m = row._mapping
    return RunnerProfile(
        id=m["id"],
        name=m["name"],
        description=m.get("description"),
        backend=m["backend"],
        provider=m.get("provider"),
        model=m.get("model"),
        base_url=m.get("base_url"),
        api_key_env=m.get("api_key_env"),
        api_token_id=m.get("api_token_id"),
        output_mode=m.get("output_mode") or "auto",
        params=_json.loads(m.get("params_json") or "{}"),
        headers=_json.loads(m.get("headers_json") or "{}"),
        extra_args=_json.loads(m.get("extra_args_json") or "[]"),
        is_enabled=bool(m.get("is_enabled", 1)),
        is_system_default=bool(m.get("is_system_default", 0)),
        created_at=m["created_at"],
        updated_at=m["updated_at"],
    )
