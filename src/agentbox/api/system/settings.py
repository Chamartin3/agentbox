"""/api/settings — DB-backed typed-section settings store.

GET /api/settings                — list section names.
GET /api/settings/deployment     — read-only view of the AGENTBOX_* env config.
GET /api/settings/env-secrets    — names (not values) of secrets in the .env files.
GET /api/settings/{section}      — read one section (returns ``{key: value}``).
PATCH /api/settings/{section}    — partial patch; only listed keys change.
"""

from __future__ import annotations

from typing import TypedDict, cast

from dotenv import dotenv_values
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.config import SETTINGS

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ListSettingsResult(TypedDict):
    """Response envelope for GET /api/settings."""

    known: list[str]
    present: list[str]


class GetSettingsResult(TypedDict):
    """Response envelope for GET /api/settings/{section}."""

    section: str
    values: dict
    defaults: dict
    overrides: dict


class PatchSettingsResult(TypedDict):
    """Response envelope for PATCH /api/settings/{section}."""

    section: str
    values: dict

# Known sections — the UI uses these to render typed tabs. Storing them
# here (not enforced in DB) means a new section ships with a code change,
# which keeps casual writes from creating sprawl.
KNOWN_SECTIONS = (
    "runtime_defaults",
    "mcp_global",
    "secrets",
)


# Default seed values surfaced when a section has nothing in the DB yet.
# Backends read these via ``agentbox.core.engines.defaults.runtime_default_model``
# at runtime — editing them in the UI takes effect on the next run.
SECTION_DEFAULTS: dict[str, dict] = {
    "runtime_defaults": {
        "timeout_seconds": 1200,
        # Applied as the initial values when a NEW agent is created. Runtime
        # always reads the agent's own config, never these — see AgentNew.tsx.
        "max_error_retries": 0,
        "max_validation_retries": 1,
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
) -> ListSettingsResult:
    return {
        "known": list(KNOWN_SECTIONS),
        "present": ctx.system.list_settings_sections(),
    }


class DeploymentEntry(TypedDict):
    name: str
    env: str  # the AGENTBOX_* var that sets it ("" for derived values)
    value: str  # rendered current value; secrets shown as "set" / "unset"


class DeploymentResult(TypedDict):
    """Read-only view of the process env config (the SETTINGS singleton)."""

    groups: dict[str, list[DeploymentEntry]]


def _deployment_groups() -> dict[str, list[DeploymentEntry]]:
    s = SETTINGS
    mask = lambda v: "set" if v else "unset"  # noqa: E731 — never leak secret values

    def e(name: str, env: str, value: object) -> DeploymentEntry:
        return {"name": name, "env": env, "value": "" if value is None else str(value)}

    return {
        "Paths": [
            e("data_dir", "AGENTBOX_DATA_DIR", s.data_dir),
            e("db_path", "(derived)", s.db_path),
            e("project_root", "AGENTBOX_ROOT_DIR", s.project_root),
            e("workspaces_root", "(derived)", s.workspaces_root),
            e("creds_dir", "AGENTBOX_CREDS_DIR", s.creds_dir),
            e("creds_env_file", "(derived)", s.creds_env_file),
            e("agents_dir", "AGENTBOX_AGENTS_DIR", s.agents_dir),
            e("prompts_dir", "AGENTBOX_PROMPTS_DIR", s.prompts_dir),
            e("skills_dir", "AGENTBOX_SKILLS_DIR", s.skills_dir),
            e("outputs_dir", "AGENTBOX_OUTPUTS_DIR", s.outputs_dir),
        ],
        "Server": [
            e("host", "AGENTBOX_HOST", s.host),
            e("port", "AGENTBOX_PORT", s.port),
            e("completion_webhook_url", "AGENTBOX_COMPLETION_WEBHOOK_URL", s.completion_webhook_url),
            e("webhook_secret", "AGENTBOX_WEBHOOK_SECRET", mask(s.webhook_secret)),
            e("secret_key", "AGENTBOX_SECRET_KEY", mask(s.secret_key)),
        ],
        "MCP": [
            e("mcp_transport", "AGENTBOX_MCP_TRANSPORT", s.mcp_transport),
            e("mcp_host", "AGENTBOX_MCP_HOST", s.mcp_host),
            e("mcp_port", "AGENTBOX_MCP_PORT", s.mcp_port),
            e("mcp_discovery_ttl", "AGENTBOX_MCP_DISCOVERY_TTL", s.mcp_discovery_ttl),
        ],
        "Environment": [
            e("in_container", "AGENTBOX_IN_CONTAINER", s.in_container),
            e("ollama_url_rewrite", "AGENTBOX_OLLAMA_URL_REWRITE", s.ollama_url_rewrite),
        ],
    }


@router.get("/deployment")
def get_deployment() -> DeploymentResult:
    """Read-only. These come from AGENTBOX_* env vars, read once at startup;
    changing them means editing the env / .env and restarting the server."""
    return {"groups": _deployment_groups()}


class EnvSecretsResult(TypedDict):
    """Secret *names* (never values) discovered in the on-disk .env files."""

    names: list[str]
    files: list[str]


@router.get("/env-secrets")
def get_env_secrets() -> EnvSecretsResult:
    """Names of keys present in the creds .env file. Values are never returned."""
    files: list[str] = []
    names: set[str] = set()
    creds_env = SETTINGS.creds_env_file
    if creds_env.exists():
        files.append(str(creds_env))
        names.update(k for k in dotenv_values(creds_env) if k)
    return {"names": sorted(names), "files": files}


@router.get("/{section}")
def get_section(
    section: str,
    ctx: APIContext = Depends(get_api_context),
) -> GetSettingsResult:
    """Return the section. Missing keys are filled from `SECTION_DEFAULTS`
    so the UI shows the active fallback values, not an empty object.
    """
    stored = ctx.system.get_settings_section(section)
    seeded = dict(SECTION_DEFAULTS.get(section, {}))
    seeded.update(stored)
    return cast(
        GetSettingsResult,
        {
            "section": section,
            "values": seeded,
            "defaults": SECTION_DEFAULTS.get(section, {}),
            "overrides": stored,
        },
    )


@router.patch("/{section}")
def patch_section(
    section: str,
    body: PatchBody,
    ctx: APIContext = Depends(get_api_context),
) -> PatchSettingsResult:
    updated = ctx.system.update_settings_section(section, body.values)
    return cast(PatchSettingsResult, {"section": section, "values": updated})
