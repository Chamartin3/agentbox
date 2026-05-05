"""Runner backend discovery API.

Lists registered backend adapters and the providers they're compatible
with, so the UI can render backend pickers, filter the provider
dropdown, and show the right model-selection affordance per backend.

Endpoint:
  GET /api/runner-backends  — list backends with compatible providers
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agentbox.core.plugins import backends as registered_backends
from agentbox.core.providers import list_providers

router = APIRouter(prefix="/api/runner-backends", tags=["runner-backends"])


class BackendDescriptor(BaseModel):
    """UI-facing description of a registered backend."""

    id: str
    label: str
    default_model: str | None = None
    compatible_providers: list[str] = Field(default_factory=list)
    accepts_no_provider: bool = True
    """True when this backend can run without an explicit provider
    (e.g. claude_code uses the host's OAuth session)."""


_LABELS: dict[str, str] = {
    "claude_code": "Claude Code (CLI)",
    "opencode": "OpenCode (CLI)",
    "codex": "OpenAI Codex (CLI)",
    "pi": "pi.dev (CLI)",
    "token": "Token / pydantic-ai (in-process)",
}


@router.get("")
def list_runner_backends() -> list[BackendDescriptor]:
    """List every registered backend along with the providers it accepts."""
    providers = list_providers()
    out: list[BackendDescriptor] = []
    for name, cls in sorted(registered_backends().items()):
        compatible = [
            p.id for p in providers if name in (p.compatible_backends or [])
        ]
        out.append(
            BackendDescriptor(
                id=name,
                label=_LABELS.get(name, name),
                default_model=getattr(cls, "default_model", None),
                compatible_providers=compatible,
                accepts_no_provider=True,
            )
        )
    return out
