"""/api/settings — DB-backed typed-section settings store.

GET /api/settings                — list section names.
GET /api/settings/{section}      — read one section (returns ``{key: value}``).
PATCH /api/settings/{section}    — partial patch; only listed keys change.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Known sections — the UI uses these to render typed tabs. Storing them
# here (not enforced in DB) means a new section ships with a code change,
# which keeps casual writes from creating sprawl.
KNOWN_SECTIONS = (
    "runtime_defaults",
    "workspace_defaults",
    "mcp_global",
    "webhook",
    "telemetry",
    "secrets",
)


# Default seed values surfaced when a section has nothing in the DB yet.
# Backends read these via ``agentbox.core.engines.defaults.runtime_default_model``
# at runtime — editing them in the UI takes effect on the next run.
SECTION_DEFAULTS: dict[str, dict] = {
    "runtime_defaults": {
        "timeout_seconds": 1200,
        "default_model_opencode": "opencode/deepseek-v4-flash-free",
        "default_model_codex": None,
        "default_model_pi": None,
    },
}


class PatchBody(BaseModel):
    """Partial patch — values are arbitrary JSON-serializable."""

    values: dict


@router.get("")
def list_sections(
    ctx: APIContext = Depends(get_api_context),
) -> dict:
    return {
        "known": list(KNOWN_SECTIONS),
        "present": ctx.system.list_settings_sections(),
    }


@router.get("/{section}")
def get_section(
    section: str,
    ctx: APIContext = Depends(get_api_context),
) -> dict:
    """Return the section. Missing keys are filled from `SECTION_DEFAULTS`
    so the UI shows the active fallback values, not an empty object.
    """
    stored = ctx.system.get_settings_section(section)
    seeded = dict(SECTION_DEFAULTS.get(section, {}))
    seeded.update(stored)
    return {
        "section": section,
        "values": seeded,
        "defaults": SECTION_DEFAULTS.get(section, {}),
        "overrides": stored,
    }


@router.patch("/{section}")
def patch_section(
    section: str,
    body: PatchBody,
    ctx: APIContext = Depends(get_api_context),
) -> dict:
    updated = ctx.system.update_settings_section(section, body.values)
    return {"section": section, "values": updated}
