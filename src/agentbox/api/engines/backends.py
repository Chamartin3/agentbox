"""Runner backend discovery API.

Lists registered backend adapters and the providers they're compatible
with, so the UI can render backend pickers, filter the provider
dropdown, and show the right model-selection affordance per backend.

Endpoint:
  GET /api/runner-backends  — list backends with compatible providers
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.data.constants import BackendName

router = APIRouter(prefix="/api/runner-backends", tags=["runner-backends"])


class BackendDescriptor(BaseModel):
    """UI-facing description of a registered backend."""

    id: str
    label: str
    default_model: str | None = None
    compatible_providers: list[str] = Field(default_factory=list)
    accepts_no_provider: bool = True


@router.get("")
def list_runner_backends(
    ctx: APIContext = Depends(get_api_context),
) -> list[BackendDescriptor]:
    """List every registered backend along with the providers it accepts."""
    providers = ctx.engines.list_providers()
    out: list[BackendDescriptor] = []
    for name, cls in sorted(ctx.engines.backends().items()):
        compatible = [p.id for p in providers if name in (p.compatible_backends or [])]
        out.append(
            BackendDescriptor(
                id=name,
                label=BackendName.label_for(name),
                default_model=getattr(cls, "default_model", None),
                compatible_providers=compatible,
                accepts_no_provider=True,
            )
        )
    return out
