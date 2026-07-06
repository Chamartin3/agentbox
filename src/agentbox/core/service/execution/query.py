"""Run query — list_runs, run_stats, run_facets, get_run_detail."""

from __future__ import annotations

import json as _json
from collections.abc import Mapping

from agentbox.core.data.payload_types import RunFacetsResult
from agentbox.core.db import AgentVersionManager
from agentbox.core.service.evaluation.service import EvaluationService
from agentbox.core.service.execution.service import ExecutionService
from agentbox.core.service.execution.types import RunNotFound


def _svc() -> ExecutionService:
    return ExecutionService()


def _enrich_with_version(agent_versions: "AgentVersionManager", d: Mapping[str, object]) -> dict[str, object]:
    result_dict: dict[str, object] = dict(d)
    vid = d.get("agent_version_id")
    if vid is not None and isinstance(vid, int):
        v = agent_versions.get_by_id(vid)
        result_dict["agent_version"] = v["version"] if v else None
    else:
        result_dict["agent_version"] = None
    return result_dict


def list_runs(
    *,
    agent_versions: "AgentVersionManager",
    agent: str | None = None,
    status: str | None = None,
    executor: str | None = None,
    agent_version: int | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
    offset: int = 0,
    paginated: bool = False,
    with_usage: bool = False,
) -> list[dict] | dict:
    """Backward-compatible run listing."""
    svc = _svc()
    if not paginated and not any(
        [status, executor, q, since, until, offset, agent_version]
    ):
        result: list[dict] = [
            _enrich_with_version(agent_versions, r)
            for r in svc.list_runs(limit=limit, agent_id=agent)
        ]
        if with_usage:
            for d in result:
                d["usage"] = svc.get_usage(d["id"])
        return result
    items, total = EvaluationService().list_runs_paged(
        agent_id=agent,
        status=status,
        executor=executor,
        agent_version=agent_version,
        q=q,
        since_iso=since,
        until_iso=until,
        limit=limit,
        offset=offset,
    )
    enriched = [_enrich_with_version(agent_versions, r) for r in items]
    if with_usage:
        for d in enriched:
            d["usage"] = svc.get_usage(str(d["id"]))
    return {
        "items": enriched,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }


def run_stats(
    *,
    agent: str | None = None,
    status: str | None = None,
    executor: str | None = None,
    agent_version: int | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    return EvaluationService().stats_for_filters(
        agent_id=agent,
        status=status,
        executor=executor,
        agent_version=agent_version,
        q=q,
        since_iso=since,
        until_iso=until,
    )


def run_facets() -> RunFacetsResult:
    return {
        "agents": EvaluationService().distinct_agent_ids(),
        "executors": EvaluationService().distinct_executors(),
        "statuses": ["ok", "error", "failed", "timeout", "incomplete", "running"],
    }


def get_run_detail(run_id: str, *, agent_versions: "AgentVersionManager") -> dict:
    svc = _svc()
    rec = svc.get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    usage = svc.get_usage(run_id)
    run_dict = rec.model_dump() if hasattr(rec, "model_dump") else dict(rec.__dict__)
    if rec.agent_version_id is not None:
        ver = agent_versions.get_by_id(rec.agent_version_id)
        if ver is not None:
            run_dict["agent_version"] = ver.get("version")

    snap_raw = run_dict.get("runner_snapshot")
    snap: dict | None = None
    if isinstance(snap_raw, str) and snap_raw:
        try:
            snap = _json.loads(snap_raw)
            run_dict["runner_snapshot"] = snap
        except ValueError:
            run_dict["runner_snapshot"] = {"snapshot": "invalid", "raw": snap_raw}
    elif not snap_raw and rec.runner_profile_id:
        run_dict["runner_snapshot"] = {"snapshot": "missing"}

    run_dict["backend"] = snap.get("backend") if isinstance(snap, dict) else None
    run_dict["configured_model"] = (
        snap.get("model") if isinstance(snap, dict) else None
    )
    run_dict["reported_model"] = usage.get("model") if usage else None
    return {"run": run_dict, "usage": usage}


def get_run_prompt(run_id: str) -> dict:
    svc = _svc()
    rec = svc.get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    raw = svc.get_run_prompt(run_id)
    fragments = _json.loads(raw) if raw else []
    total = sum(int(f.get("size_bytes") or 0) for f in fragments)
    return {"run_id": run_id, "fragments": fragments, "total_bytes": total}
