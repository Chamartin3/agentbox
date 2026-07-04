"""Shared models used by both profiles.py and stats.py — no intra-package imports."""

from __future__ import annotations

import json as _json

from sqlalchemy.engine import Row

from agentbox.core.data.profiles import RunnerProfile


def _row_to_profile(row: Row) -> RunnerProfile:
    """Convert a database row to a RunnerProfile model."""

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
