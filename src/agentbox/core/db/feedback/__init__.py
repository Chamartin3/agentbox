"""Activity analytics: rollups, time-series, per-agent / per-executor splits.

Composed into ``SessionStore`` alongside ``_CoreStore`` and
``PromptVersionsMixin``. All methods read ``self.engine`` and depend on
the tables defined in ``data.schema``.

Sub-modules:
- activity: activity_summary, aggregate_usage, distinct listers
- aggregates: stats_for_filters with breakdowns
- listing: list_runs_paged, list_runs_rich
"""

from __future__ import annotations


from agentbox.core.db.feedback.activity import ActivityAnalyticsMixin
from agentbox.core.db.feedback.aggregates import AggregateAnalyticsMixin
from agentbox.core.db.feedback.listing import ListingAnalyticsMixin


class ExecutionAnalyticsMixin(
    ActivityAnalyticsMixin,
    AggregateAnalyticsMixin,
    ListingAnalyticsMixin,
):
    """Read-only analytics queries. Requires ``self.engine: Engine``."""
