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
    universal: bool = False  # True when the backend works with every provider
    supports_mcp: bool = True  # False for backends that cannot invoke MCP servers (e.g. pi, codex)
    native_tools: list[str] = Field(default_factory=list)  # canonical tool values the backend can natively run


@router.get("")
def list_runner_backends(
    ctx: APIContext = Depends(get_api_context),
) -> list[BackendDescriptor]:
    """List every registered backend along with the providers it accepts."""
    providers = ctx.engines.list_providers()
    out: list[BackendDescriptor] = []
    for name, cls in sorted(ctx.engines.backends().items()):
        universal: bool = getattr(cls, "universal_provider", False)
        if universal:
            compatible = [p.id for p in providers if p.requires_api_key]
        else:
            compatible = [p.id for p in providers if name in (p.compatible_backends or [])]

        supports_mcp: bool = getattr(cls, "supports_mcp", True)
        raw_native: object = getattr(cls, "NATIVE_TOOLS", None)
        native_tools: list[str] = (
            [str(k.value) for k in raw_native] if isinstance(raw_native, dict) else []
        )

        out.append(
            BackendDescriptor(
                id=name,
                label=BackendName.label_for(name),
                default_model=getattr(cls, "default_model", None),
                compatible_providers=compatible,
                accepts_no_provider=True,
                universal=universal,
                supports_mcp=supports_mcp,
                native_tools=native_tools,
            )
        )
    return out
