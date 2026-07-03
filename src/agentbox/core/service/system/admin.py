"""System admin free functions.

Thin pass-through to ``SystemService`` for facade callers. Relocated from the
former top-level ``core.service.workspace_admin`` bridge so host-env call
history lives in the system domain that owns it.
"""

from __future__ import annotations

from agentbox.core.service.system.service import SystemService


def list_host_env_calls_for_run(run_id: str) -> list[dict]:
    return SystemService().list_host_env_calls_for_run(run_id)
