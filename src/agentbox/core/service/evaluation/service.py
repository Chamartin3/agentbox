"""EvaluationService — run/agent analytics (plan 093).

The read-only analytics domain: usage & cost aggregates, activity summaries,
paginated/rich run listings, and filtered stats. Self-wiring like every
``Service``; owns no writes.

Analytics is query-centric: the aggregate SQL (and its natural row shaping)
lives on the Data layer — ``RunManager`` (run-centric, joins usage/agent_versions)
and ``UsageManager`` (usage aggregates). This service orchestrates them; there is
no cross-domain business logic here, so it calls the managers directly (per
CORE_ARCHITECTURE.md, a Service may use Managers directly for query passthrough).

ponytail: analytics returns are nested ``dict`` response shapes; a full
TypedDict pass over them is deferred (tracked with plan 094's typing work).
"""
from __future__ import annotations

from agentbox.core.service.base import Service


class EvaluationService(Service):
    """Run/agent analytics — usage, cost, activity, stats, listings."""

    def __init__(self) -> None:
        super().__init__()
        self._runs = self._db.runs
        self._usage = self._db.usage

    def aggregate_usage(self) -> dict:
        return self._usage.aggregate_usage()

    def distinct_executors(self) -> list[str]:
        return self._usage.distinct_executors()

    def distinct_agent_ids(self) -> list[str]:
        return self._runs.distinct_agent_ids()

    def activity_summary(self, since_iso: str, agent: str | None = None) -> dict:
        return self._runs.activity_summary(since_iso, agent)

    def stats_for_filters(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        agent_version: int | None = None,
        q: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
    ) -> dict:
        return self._runs.stats_for_filters(
            agent_id=agent_id,
            status=status,
            executor=executor,
            agent_version=agent_version,
            q=q,
            since_iso=since_iso,
            until_iso=until_iso,
        )

    def list_runs_paged(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        agent_version: int | None = None,
        q: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        return self._runs.list_runs_paged(
            agent_id=agent_id,
            status=status,
            executor=executor,
            agent_version=agent_version,
            q=q,
            since_iso=since_iso,
            until_iso=until_iso,
            limit=limit,
            offset=offset,
        )

    def list_runs_rich(
        self,
        since_iso: str,
        agent: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return self._runs.list_runs_rich(since_iso, agent, status, executor, limit)
