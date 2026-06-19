"""Run lifecycle, query, stream, and evaluation services.

Public callers (api/, cli/, mcp/) MUST import from this facade. The
submodules are private organisation.
"""

from agentbox.core.service.execution.create import create_run, rerun
from agentbox.core.service.execution.feedback import (
    activity_summary,
    add_comment,
    aggregate_usage,
    distinct_executors,
    list_comments,
)
from agentbox.core.service.execution.lifecycle import (
    cancel_run,
    complete_run,
    post_outcome,
    snapshot_run,
)
from agentbox.core.service.execution.query import (
    get_run_detail,
    get_run_prompt,
    list_runs,
    run_facets,
    run_stats,
)
from agentbox.core.service.execution.stream import get_transcript
from agentbox.core.service.execution.types import InvalidRunInput, RunNotFound, no_backend_detail
from agentbox.core.service.prompts import AgentNotFound

__all__ = [
    "activity_summary",
    "add_comment",
    "aggregate_usage",
    "AgentNotFound",
    "cancel_run",
    "complete_run",
    "create_run",
    "distinct_executors",
    "get_run_detail",
    "get_run_prompt",
    "get_transcript",
    "InvalidRunInput",
    "list_comments",
    "list_runs",
    "no_backend_detail",
    "post_outcome",
    "rerun",
    "run_facets",
    "RunNotFound",
    "run_stats",
    "snapshot_run",
]
