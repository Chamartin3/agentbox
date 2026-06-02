"""Service layer for run orchestration.

The HTTP layer (`api/routes/runs.py`) becomes a thin transport adapter:
parse request → call into here → translate domain errors to HTTP.
The MCP layer can reuse the same use-cases without round-tripping
through FastAPI.

Domain errors raised here:

* :class:`AgentNotFound` — re-exported from ``core.service.prompts``.
* :class:`RunNotFound` — unknown ``run_id``.
* :class:`InvalidRunInput` — caller provided neither ``input`` nor
  ``variables`` when both are required.

The executor's :class:`NoBackendAvailable` is intentionally NOT
caught here; callers decide how to surface "the server can't fulfil
this dispatch right now". :func:`no_backend_detail` is exposed so
both REST and MCP can render the same explanation string.
"""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.agents.resolve import (
    engine_load_failure as backend_load_failure,
    list_engines as backends,
)
from agentbox.core.data import read_transcript
from agentbox.core.run.executor import NoBackendAvailable
from agentbox.core.service.agents import resolve_agent
from agentbox.core.service.prompts import AgentNotFound

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore
    from agentbox.core.run.executor import RunExecutor

logger = logging.getLogger(__name__)

__all__ = [
    "AgentNotFound",
    "RunNotFound",
    "InvalidRunInput",
    "NoBackendAvailable",
    "no_backend_detail",
    "create_run",
    "list_runs",
    "run_stats",
    "run_facets",
    "complete_run",
    "snapshot_run",
    "post_outcome",
    "rerun",
    "cancel_run",
    "list_comments",
    "add_comment",
    "get_run_detail",
    "get_run_prompt",
    "get_transcript",
]


class RunNotFound(LookupError):
    """Raised when no run exists for ``run_id``."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"unknown run {run_id!r}")
        self.run_id = run_id


class InvalidRunInput(ValueError):
    """Raised when the run dispatch payload is missing required fields."""


# ---------------------------------------------------------------------------
# Backend error explanation
# ---------------------------------------------------------------------------


def no_backend_detail(exc: NoBackendAvailable) -> str:
    """Compose an honest 'why is no backend available' message.

    For each backend the executor *tried* to use, report whether it was
    never registered or whether it's registered but failed to import at
    startup (with the real exception text). Never says "promote a version"
    — the agent config is fine; the *server* can't fulfil the request.
    """
    loaded = set(backends().keys())
    parts: list[str] = []
    for name in exc.attempted:
        failure = backend_load_failure(name)
        if failure is not None:
            parts.append(f"{name!r} failed to load at startup: {failure}")
        elif name not in loaded:
            parts.append(f"{name!r} is not a registered backend")
        else:
            parts.append(f"{name!r} failed to instantiate")
    why = "; ".join(parts) if parts else "no backend candidates were derived"
    return (
        f"agent {exc.agent_id!r}: cannot dispatch — {why}. "
        f"Registered backends: {sorted(loaded)}."
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def create_run(
    agent_id: str,
    *,
    store: SessionStore,
    executor: RunExecutor,
    input_: str | None = None,
    variables: dict[str, str] | None = None,
    session_id: str | None = None,
    workspace: str | None = None,
    timeout_seconds: int | None = None,
    webhook_url: str | None = None,
    runner: str | None = None,
    backend: str | None = None,
    runner_profile: str | None = None,
    runner_config: dict[str, Any] | None = None,
    runner_embedded: bool = False,
    loader: Any = None,
) -> dict:
    """Validate input, resolve the agent, and dispatch to the executor.

    Raises :class:`AgentNotFound`, :class:`InvalidRunInput`, or
    :class:`NoBackendAvailable`. Returns ``{"run_id", "agent"}``.
    """
    agent = resolve_agent(agent_id, store=store, loader=loader)
    if agent is None:
        raise AgentNotFound(agent_id)

    # Legacy free-text input path
    if input_ is not None and variables is None:
        if agent.composition is not None:
            logger.warning(
                "run for agent %r uses legacy 'input' but agent has [composition]; "
                "migrate to 'variables' with 'user_message'",
                agent.id,
            )
        run_id = await executor.execute(
            agent,
            input_,
            session_id=session_id,
            workspace_override=workspace,
            timeout_seconds=timeout_seconds,
            webhook_url=webhook_url,
            runner_override=runner,
            backend=backend,
            runner_profile=runner_profile,
            runner_config=runner_config,
        )
        return {"run_id": run_id, "agent": agent.id}

    if variables is None:
        raise InvalidRunInput("either 'input' or 'variables' must be provided")

    run_id = await executor.execute(
        agent,
        "",  # composition derives the user message from variables
        variables=variables,
        session_id=session_id,
        workspace_override=workspace,
        timeout_seconds=timeout_seconds,
        webhook_url=webhook_url,
        runner_override=runner,
        backend=backend,
        runner_profile=runner_profile,
        runner_config=runner_config,
        runner_embedded=runner_embedded,
    )
    return {"run_id": run_id, "agent": agent.id}


async def rerun(
    run_id: str,
    *,
    store: SessionStore,
    executor: RunExecutor,
    loader: Any = None,
) -> dict:
    """Re-execute a finished run with the same agent + input/variables."""
    rec = store.get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    agent = resolve_agent(rec.agent_id, store=store, loader=loader)
    if agent is None:
        raise AgentNotFound(rec.agent_id)

    variables: dict[str, str] | None = None
    if rec.variables:
        try:
            parsed = (
                _json.loads(rec.variables)
                if isinstance(rec.variables, str)
                else rec.variables
            )
            if isinstance(parsed, dict):
                variables = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            variables = None

    new_id = await executor.execute(
        agent,
        rec.input or "",
        variables=variables,
        session_id=None,
        workspace_override=None,
    )
    return {"run_id": new_id, "agent": agent.id, "rerun_of": run_id}


async def cancel_run(
    run_id: str,
    *,
    store: SessionStore,
    executor: RunExecutor,
) -> dict:
    """Cancel an in-progress run. Idempotent on terminal runs."""
    existing = store.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    if existing.status != "running":
        return {"run_id": run_id, "cancelled": False, "status": existing.status}
    cancelled = await executor.cancel_run(run_id)
    refreshed = store.get_run(run_id) or existing
    return {"run_id": run_id, "cancelled": cancelled, "status": refreshed.status}


# ---------------------------------------------------------------------------
# Listing / facets / stats
# ---------------------------------------------------------------------------


def _enrich_with_version(store: SessionStore, d: dict) -> dict:
    vid = d.get("agent_version_id")
    if vid is not None:
        v = store.get_version_by_id(vid)
        d["agent_version"] = v["version"] if v else None
    else:
        d["agent_version"] = None
    return d


def list_runs(
    *,
    store: SessionStore,
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
    """Backward-compatible run listing.

    Returns the raw list when called without filters; otherwise returns
    the envelope ``{items, total, offset, limit, has_more}``.

    When ``with_usage`` is True, each run dict is enriched with a
    ``usage`` key containing the corresponding usage record (or ``None``).
    """
    if not paginated and not any(
        [status, executor, q, since, until, offset, agent_version]
    ):
        result: list[dict] = [
            _enrich_with_version(store, r.__dict__)
            for r in store.list_runs(limit=limit, agent_id=agent)
        ]
        if with_usage:
            for d in result:
                d["usage"] = store.get_usage(d["id"])
        return result
    items, total = store.list_runs_paged(
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
    enriched = [_enrich_with_version(store, r) for r in items]
    if with_usage:
        for d in enriched:
            d["usage"] = store.get_usage(d["id"])
    return {
        "items": enriched,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }


def run_stats(
    *,
    store: SessionStore,
    agent: str | None = None,
    status: str | None = None,
    executor: str | None = None,
    agent_version: int | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    return store.stats_for_filters(
        agent_id=agent,
        status=status,
        executor=executor,
        agent_version=agent_version,
        q=q,
        since_iso=since,
        until_iso=until,
    )


def run_facets(*, store: SessionStore) -> dict:
    return {
        "agents": store.distinct_agent_ids(),
        "executors": store.distinct_executors(),
        "statuses": ["ok", "error", "failed", "timeout", "incomplete", "running"],
    }


# ---------------------------------------------------------------------------
# Lifecycle (complete / snapshot / post_outcome)
# ---------------------------------------------------------------------------


def complete_run(
    run_id: str,
    *,
    store: SessionStore,
    ok: bool,
    output: str | None,
    error: str | None,
    usage: dict | None,
    loader: Any = None,
    schedule_webhook_cb: Any = None,
) -> dict:
    """Finalize a run from an external worker.

    ``schedule_webhook_cb(agent, refreshed, store)`` is invoked after
    state transitions so the HTTP layer can wire its own webhook
    scheduler without this module depending on ``api.webhooks``.
    """
    existing = store.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    if existing.status not in {"ok", "error"}:
        store.finish_run(run_id, ok=ok, output=output, error=error)
    if usage:
        try:
            store.record_usage(run_id, usage)
        except Exception as exc:
            logger.warning("record_usage failed for %s: %s", run_id, exc)

    refreshed = store.get_run(run_id) or existing
    if schedule_webhook_cb is not None:
        agent = resolve_agent(refreshed.agent_id, store=store, loader=loader)
        schedule_webhook_cb(agent, refreshed, store)
    return {"ok": True, "run_id": run_id, "status": refreshed.status}


def snapshot_run(
    run_id: str,
    *,
    store: SessionStore,
    rendered_prompt: dict,
    variables: dict,
    response_raw: str,
    validation_status: str = "ok",
    validation_errors: list[str] | None = None,
    composition_snapshot: dict | None = None,
    loader: Any = None,
    schedule_webhook_cb: Any = None,
) -> dict:
    """Store a snapshot for an embedded run; idempotent on terminal runs."""
    existing = store.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    if existing.rendered_prompt is not None:
        logger.warning("snapshot_run: overwriting existing snapshot for %s", run_id)

    store.save_run_snapshot(
        run_id=run_id,
        rendered_prompt=rendered_prompt,
        variables=variables,
        validation_status=validation_status,
        validation_errors=validation_errors or [],
        composition_snapshot=composition_snapshot,
    )

    if existing.status not in {"ok", "error"}:
        store.finish_run(
            run_id,
            ok=validation_status != "fail",
            output=response_raw,
            error=None if validation_status != "fail" else "validation failed",
        )

    refreshed = store.get_run(run_id) or existing
    if schedule_webhook_cb is not None:
        agent = resolve_agent(refreshed.agent_id, store=store, loader=loader)
        if agent is not None:
            schedule_webhook_cb(agent, refreshed, store)
    return {"ok": True, "run_id": run_id}


def post_outcome(
    run_id: str,
    *,
    store: SessionStore,
    status: str,
    error_kind: str | None = None,
    errors: list[dict] | None = None,
) -> dict:
    existing = store.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    store.set_run_post_outcome(
        run_id, ok=(status == "ok"), error_kind=error_kind, errors=errors
    )
    refreshed = store.get_run(run_id) or existing
    return {"ok": True, "run_id": run_id, "post_status": refreshed.post_status}


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def list_comments(run_id: str, *, store: SessionStore) -> dict:
    if store.get_run(run_id) is None:
        raise RunNotFound(run_id)
    return {"run_id": run_id, "comments": store.list_run_comments(run_id)}


def add_comment(
    run_id: str, *, store: SessionStore, author: str, body: str
) -> dict:
    if store.get_run(run_id) is None:
        raise RunNotFound(run_id)
    return store.add_run_comment(run_id, author, body)


# ---------------------------------------------------------------------------
# Detail views (used by GET /api/runs/{id})
# ---------------------------------------------------------------------------


def get_run_detail(run_id: str, *, store: SessionStore) -> dict:
    rec = store.get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    usage = store.get_usage(run_id)
    run_dict = dict(rec.__dict__)
    if rec.agent_version_id is not None:
        ver = store.get_version_by_id(rec.agent_version_id)
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


def get_run_prompt(run_id: str, *, store: SessionStore) -> dict:
    rec = store.get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    raw = store.get_run_prompt(run_id)
    fragments = _json.loads(raw) if raw else []
    total = sum(int(f.get("size_bytes") or 0) for f in fragments)
    return {"run_id": run_id, "fragments": fragments, "total_bytes": total}


def get_transcript(run_id: str, *, store: SessionStore) -> list[dict]:
    rec = store.get_run(run_id)
    if rec is None or not rec.transcript_path:
        raise RunNotFound(run_id)
    return read_transcript(Path(rec.transcript_path))
