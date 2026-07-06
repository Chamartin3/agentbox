"""Per-agent validation: inline ``config_json[direction].validators`` endpoints.

Two endpoints:

- ``GET  /api/agents/{id}/validation`` — read the active version's
  inline validators for both directions.
- ``PUT  /api/agents/{id}/validation`` — write inline validators by
  creating a NEW ``agent_versions`` row that carries everything
  forward (prompt, config, snapshot, files) and then mutating just
  ``config_json[direction].validators``. Activating that version
  makes the change live.

The schema (input/output structural shape) is NOT touched here — it
lives in ``agent_prompt_resource_bindings`` with slot=``input_schema``
or ``output_schema``.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.data.payload_types import AgentValidationResult
from agentbox.core.service.agents import AgentServiceError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-validation"])


class HttpValidatorIn(BaseModel):
    kind: Literal["http"] = "http"
    endpoint: str
    timeout_seconds: int = 5
    description: str = ""


class ScriptValidatorIn(BaseModel):
    kind: Literal["script"] = "script"
    resource_id: str
    pinned_version_id: str | None = None
    description: str = ""


ValidatorIn = HttpValidatorIn | ScriptValidatorIn


class DirectionBody(BaseModel):
    """Validators payload for a single direction. ``null`` clears the
    direction; an empty list also clears it (no validators); anything
    else replaces wholesale."""

    validators: list[dict] = Field(default_factory=list)


class AgentValidationPut(BaseModel):
    input: DirectionBody | None = None
    output: DirectionBody | None = None
    reason: str = Field(default="validation edit", min_length=1)
    actor: str | None = None


@router.get("/api/agents/{agent_id}/validation")
def get_agent_validation(
    agent_id: str,
    ctx: APIContext = Depends(get_api_context),
) -> AgentValidationResult:
    """Return the active version's inline validators per direction."""
    return ctx.agents.get_agent_validation(agent_id)


@router.put("/api/agents/{agent_id}/validation")
def put_agent_validation(
    agent_id: str,
    body: AgentValidationPut,
    ctx: APIContext = Depends(get_api_context),
) -> AgentValidationResult:
    """Write inline validators by minting a new active version.

    Omitting a direction in the body leaves it unchanged on the new
    version (carried forward from prior ``config_json``). Passing
    ``{"validators": []}`` clears that direction.
    """
    input_validators = (
        body.input.validators
        if "input" in body.model_fields_set and body.input is not None
        else None
    )
    output_validators = (
        body.output.validators
        if "output" in body.model_fields_set and body.output is not None
        else None
    )
    try:
        return ctx.agents.put_agent_validation(
            agent_id,
            input_validators=input_validators,
            output_validators=output_validators,
            reason=body.reason,
            actor=body.actor,
        )
    except AgentServiceError as exc:
        raise HTTPException(
            exc.status_code, {"code": exc.code, "detail": exc.detail}
        ) from exc
