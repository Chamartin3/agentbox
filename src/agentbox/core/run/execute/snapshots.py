"""Build and persist the immutable snapshots attached to a run row.

A "snapshot" is the historical fact of what configuration was actually
used for a run — runner profile + backend + model, resolved MCP server
list, resource bindings. The run row stores these append-only so the
UI can render exactly what executed even after the underlying profile,
workspace, or agent is renamed/rebound/deleted.

This module owns:

* :func:`build_runner_snapshot` — turn an ``EffectiveRunnerConfig`` plus
  the request-level overrides into the ``RunnerSnapshot`` dict.
* :class:`SnapshotWriter` — best-effort persist of runner / MCP /
  resource snapshots; logs and swallows on failure (snapshot loss is
  surface-area degradation, never a reason to fail the run).
"""

from __future__ import annotations

import logging
from typing import Any

from agentbox.core.agent.profiles import EffectiveRunnerConfig
from agentbox.core.data import AgentDef, McpSnapshot, RunnerSnapshot, SessionStore
from agentbox.core.tools.capabilities import (
    CAPABILITIES as _HOST_ENV_CAPABILITIES,
)

logger = logging.getLogger(__name__)


def build_runner_snapshot(
    store: SessionStore,
    *,
    effective: EffectiveRunnerConfig,
    rendered_model: str | None,
    backend_override: str | None,
    runner_override: str | None,
    runner_profile_id_param: str | None,
    runner_config_param: dict[str, Any] | None,
    timeout_override: int | None,
    agent: AgentDef,
) -> RunnerSnapshot:
    """Compose the append-only ``runner_snapshot`` dict for a run.

    Captures everything the run-detail UI needs to render what actually
    executed: backend, model, timeout, provider, extra_args, the
    resolution source, and any per-run overrides that were applied.
    Profile name is looked up best-effort.
    """
    from agentbox.core.data import now_iso

    profile_name: str | None = None
    if effective.profile_id:
        try:
            profile = store.get_runner_profile(effective.profile_id)
            if profile is not None:
                profile_name = getattr(profile, "name", None) or (
                    profile.get("name") if hasattr(profile, "get") else None
                )
        except Exception:
            logger.debug(
                "could not resolve profile name for %s", effective.profile_id
            )

    overrides_applied: dict[str, Any] = {}
    if backend_override:
        overrides_applied["backend"] = backend_override
    if runner_override:
        overrides_applied["runner_kind"] = runner_override
    if runner_profile_id_param:
        overrides_applied["runner_profile_id"] = runner_profile_id_param
    if runner_config_param:
        overrides_applied["runner_config"] = runner_config_param
    if timeout_override:
        overrides_applied["timeout_seconds"] = timeout_override

    effective_timeout = timeout_override or agent.runner.timeout_seconds

    return {
        "profile_id": effective.profile_id,
        "profile_name": profile_name,
        "backend": effective.backend,
        "model": rendered_model or effective.model,
        "timeout_seconds": effective_timeout,
        "provider": effective.provider,
        "extra_args": list(effective.extra_args or []),
        "source": effective.source,
        "overrides_applied": overrides_applied,
        "captured_at": now_iso(),
    }


class SnapshotWriter:
    """Persist the per-run runner / MCP / resource snapshots.

    Failures are logged and swallowed: snapshot loss degrades the
    run-detail page but is never a reason to fail the run itself.
    """

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def save_runner(self, run_id: str, snapshot: RunnerSnapshot) -> None:
        try:
            self._store.save_run_runner_snapshot(run_id, snapshot)
        except Exception:
            logger.exception("failed to persist runner_snapshot for run %s", run_id)

    def build_mcp_snapshot(
        self,
        *,
        workspace_id: str | None,
        host_env_grants: dict | None,
    ) -> McpSnapshot | None:
        """Resolve the workspace's effective MCP server list."""
        if not workspace_id:
            return None
        try:
            manifest_servers = [
                {
                    "name": s.name,
                    "config": {"url": s.url, "transport": str(s.transport)},
                }
                for s in self._store.get_project_mcp_servers()
            ]
            snapshot = self._store.resolve_workspace_mcp(
                workspace_id, manifest_servers
            )
            if host_env_grants:
                snapshot["host_env_grants"] = list(host_env_grants.keys())
                snapshot["host_env_injected"] = True
            return snapshot
        except Exception:
            logger.exception(
                "executor: MCP snapshot capture failed for workspace %r",
                workspace_id,
            )
            return None

    def save_resource_and_mcp(
        self,
        run_id: str,
        *,
        resource_snapshot: list | None,
        mcp_snapshot: McpSnapshot | None,
    ) -> None:
        try:
            self._store.save_resource_snapshots(
                run_id,
                resource_snapshot=resource_snapshot if resource_snapshot else None,
                mcp_snapshot=mcp_snapshot,
            )
        except Exception:
            logger.exception(
                "executor: failed to persist snapshots for run %s", run_id
            )

    def resolve_host_env_grants(self, workspace_id: str | None) -> dict | None:
        """Return the workspace's non-default host-env grants, or ``None``."""
        if not workspace_id:
            return None
        try:
            resolved_he = self._store.resolve_workspace_host_env(workspace_id)
            grants = resolved_he.get("grants") or {}
            non_default = {
                k for k, v in _HOST_ENV_CAPABILITIES.items() if not v.default_granted
            }
            if grants.keys() & non_default:
                return grants
        except Exception:
            logger.exception(
                "executor: host-env grant resolution failed for workspace %r",
                workspace_id,
            )
        return None


__all__ = ["SnapshotWriter", "build_runner_snapshot"]
