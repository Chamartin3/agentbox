"""Enrichment helpers — profile cache + runner snapshot extraction."""

import json as _json
from typing import Any

from agentbox.core.db.store import SessionStore


def _profile_cache(store: SessionStore) -> dict[str, Any]:
    """Return a shared profile cache for a batch of enrichment calls."""
    return {}


def _load_profile(store: SessionStore, cache: dict[str, Any], profile_id: str | None) -> Any:
    if not profile_id:
        return None
    if profile_id in cache:
        return cache[profile_id]
    try:
        profile = store.get_runner_profile(profile_id)
    except Exception:
        profile = None
    cache[profile_id] = profile
    return profile


def _profile_attr(
    store: SessionStore, cache: dict[str, Any], profile_id: str | None, attr: str
) -> str | None:
    profile = _load_profile(store, cache, profile_id)
    if profile is None:
        return None
    return getattr(profile, attr, None) or (
        profile.get(attr) if hasattr(profile, "get") else None
    )


def snapshot_fields(
    store: SessionStore,
    cache: dict[str, Any],
    row: dict[str, Any],
) -> tuple[str | None, str | None]:
    snap_raw = row.get("runner_snapshot")
    if snap_raw:
        try:
            snap = _json.loads(snap_raw) if isinstance(snap_raw, str) else snap_raw
            if isinstance(snap, dict):
                return snap.get("backend"), snap.get("model")
        except (ValueError, TypeError):
            pass
    profile_id = row.get("runner_profile_id")
    return _profile_attr(store, cache, profile_id, "backend"), _profile_attr(
        store, cache, profile_id, "model"
    )
