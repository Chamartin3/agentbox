"""RunRecord dataclass and related types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from pydantic import BaseModel

from agentbox.core.data.payload_types import UsagePayload


class DoctorCheck(NamedTuple):
    """One diagnostic result. Tuple-compatible: renders as ``(name, ok, detail)``."""

    name: str
    ok: bool
    detail: str


class RunSummary(BaseModel):
    """A run plus its usage totals, for the ``history ls`` listing.

    Built by ``ExecutionService.list_run_summaries`` from the ``Run`` pydantic
    models the manager returns. The renderer reads attributes directly;
    ``--json`` output dumps via ``model_dump``.
    """

    id: str
    agent_id: str
    status: str
    created_at: str
    finished_at: str | None = None
    usage: UsagePayload | None = None


@dataclass
class RunRecord:
    id: str
    agent_id: str
    session_id: str | None
    status: str
    input: str
    output: str | None
    error: str | None
    workdir: str | None
    transcript_path: str | None
    created_at: str
    finished_at: str | None
    config_digest: str | None = None
    agent_version_id: int | None = None
    composition_snapshot: str | None = None
    rendered_prompt: str | None = None
    variables: str | None = None
    validation_status: str | None = None
    validation_errors: str | None = None
    schema_validated_via: str | None = None
    post_status: str | None = None
    post_errors: str | None = None
    conversation_format: str | None = None
    conversation_uri: str | None = None
    runner_profile_id: str | None = None
    resource_snapshot: str | None = None
    mcp_snapshot: str | None = None
    runner_snapshot: str | None = None


__all__ = ["RunRecord", "DoctorCheck", "RunSummary"]

