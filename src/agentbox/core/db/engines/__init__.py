"""Engines domain — runner backend configuration profiles.

One file per table (entity + manager together). The manager is the public
surface; the entity is importable directly for cross-domain FK references.
"""
from __future__ import annotations

from agentbox.core.db.engines.runner_profile import RunnerProfile, RunnerProfileManager

__all__ = [
    "RunnerProfile",
    "RunnerProfileManager",
]
