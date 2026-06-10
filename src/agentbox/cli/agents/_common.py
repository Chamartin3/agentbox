"""Shared helpers for agent CLI commands."""

from __future__ import annotations

import json


def _set_dotted(obj: dict, dotted: str, value: object) -> None:
    """Set a nested key using dot notation on a dict."""
    parts = dotted.split(".")
    cur = obj
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _coerce(value: str) -> object:
    """Try JSON first (so ``[1,2]`` / ``true`` parse), else return the str."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
