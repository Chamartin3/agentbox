"""Agent CRUD + enriched read views — extracted from __init__.py per C10.

Import from ``service.agents`` (the package), never from this module directly.
"""

from __future__ import annotations

import logging
import types

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from agentbox.core.workspaces import workdir as ws
from agentbox.core.agents import compose_from_source, load_bundle_from_bindings
from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.db import (
    AgentDefManager,
    AgentMetaManager,
    AgentPromptResourceBindingManager,
    AgentVersionCommentManager,
    AgentVersionFileManager,
    AgentVersionManager,
    AgentVersionRatingManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
)
from agentbox.core.db.schema import agent_runner_profiles  # ponytail: transitional — plans 111/112/110/113_04 replace this with managers/Services
from agentbox.core.db.schema import runs as runs_table  # ponytail: transitional — plans 111/112/110/113_04 replace this with managers/Services
from agentbox.core.service.engines import EngineService

logger = logging.getLogger(__name__)


def resolve_agent(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
) -> AgentDef | None:
    return agent_defs.get(agent_id)


def list_all_agents(
    *,
    agent_versions: AgentVersionManager,
    agent_meta: AgentMetaManager,
    include_disabled: bool = False,
) -> list[AgentDef]:
    rows = agent_versions.list_latest_per_agent()
    hidden: set[str] = set()
    hidden |= agent_meta.agent_ids_with_deleted()
    if not include_disabled:
        hidden |= agent_meta.agent_ids_with_disabled()
    out: list[AgentDef] = []
    for row in rows:
        if row.get("agent_id") in hidden:
            continue
        try:
            agent = AgentDef.from_db_row(row)
        except ValueError:
            continue
        except Exception:
            logger.exception(
                "list_all_agents: snapshot for %r v%s failed validation",
                row.get("agent_id"),
                row.get("version"),
            )
            continue
        out.append(agent)
    return out


# ---------------------------------------------------------------------------
# Enriched read views (extracted from api/routes/agents.py)
# ---------------------------------------------------------------------------


def _aggregate_run_metadata(
    engine: Engine,
) -> tuple[dict[str, int], dict[str, str], dict[str, str]]:
    run_counts: dict[str, int] = {}
    last_run_at: dict[str, str] = {}
    profile_bindings: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            for agent_id, n, last in conn.execute(
                select(
                    runs_table.c.agent_id,
                    func.count().label("n"),
                    func.max(runs_table.c.created_at).label("last"),
                ).group_by(runs_table.c.agent_id)
            ):
                if agent_id:
                    run_counts[agent_id] = int(n)
                    if last:
                        last_run_at[agent_id] = str(last)
            for agent_id, profile_id in conn.execute(
                select(
                    agent_runner_profiles.c.agent_id,
                    agent_runner_profiles.c.runner_profile_id,
                )
            ):
                profile_bindings[agent_id] = profile_id
    except Exception:
        logger.exception(
            "list_agents_enriched: failed to load run counts / profile bindings"
        )
    return run_counts, last_run_at, profile_bindings


def _strip_legacy_runner_model(dumped: dict) -> dict:
    if isinstance(dumped.get("runner"), dict):
        dumped["runner"] = {k: v for k, v in dumped["runner"].items() if k != "model"}
    return dumped


def _enrich_agent(
    agent: AgentDef,
    *,
    agent_versions: AgentVersionManager,
    agent_meta: AgentMetaManager,
    settings: Settings,
    run_counts: dict[str, int],
    last_run_at: dict[str, str],
    profile_bindings: dict[str, str],
) -> dict:
    try:
        # ponytail: pass None for WorkspaceLookupStore — ws.resolve_path gracefully
        # falls back to settings-based path when no workspace row lookup is available.
        workspace_str = str(ws.resolve_path(agent, settings, None)[0])
    except Exception:
        workspace_str = ""
    active = agent_versions.get_active(agent.id)
    latest = agent_versions.get_latest(agent.id)
    dumped = _strip_legacy_runner_model(agent.model_dump())
    profile_id = profile_bindings.get(agent.id)
    profile = None
    if profile_id:
        try:
            profile = EngineService().get_profile(profile_id)
        except Exception:
            profile = None
    data = {
        **dumped,
        "resolved_workspace": workspace_str,
        "run_count": run_counts.get(agent.id, 0),
        "last_run_at": last_run_at.get(agent.id),
        "runner_profile_id": profile_id,
        "model": profile.model if profile else None,
        "model_provider": profile.provider if profile else None,
    }
    if latest is not None:
        data["updated_at"] = latest.get("created_at")
        data["version"] = active["version"] if active else latest.get("version")
    data["last_activity_at"] = max(
        (t for t in (data.get("updated_at"), data.get("last_run_at")) if t),
        default=None,
    )
    meta = agent_meta.get_meta(agent.id) or {}
    data["disabled_at"] = meta.get("disabled_at")
    return data


def list_agents_enriched(
    *,
    agent_versions: AgentVersionManager,
    agent_meta: AgentMetaManager,
    engine: Engine,
    settings: Settings,
    include_disabled: bool = False,
) -> list[dict]:
    run_counts, last_run_at, profile_bindings = _aggregate_run_metadata(engine)
    return [
        _enrich_agent(
            agent,
            agent_versions=agent_versions,
            agent_meta=agent_meta,
            settings=settings,
            run_counts=run_counts,
            last_run_at=last_run_at,
            profile_bindings=profile_bindings,
        )
        for agent in list_all_agents(
            agent_versions=agent_versions,
            agent_meta=agent_meta,
            include_disabled=include_disabled,
        )
    ]


def get_agent_detail(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    agent_versions: AgentVersionManager,
    agent_meta: AgentMetaManager,
    agent_version_comments: AgentVersionCommentManager,
    agent_version_ratings: AgentVersionRatingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    agent_version_files: AgentVersionFileManager,
    agent_prompt_resource_bindings: AgentPromptResourceBindingManager,
    settings: Settings,
) -> dict | None:
    agent = resolve_agent(agent_id, agent_defs=agent_defs)
    if agent is None:
        return None
    # ponytail: pass None — ws.resolve_path falls back to settings-based path.
    workspace_path, ephemeral = ws.resolve_path(agent, settings, None)

    latest_row = agent_versions.get_active(agent_id) or agent_versions.get_latest(agent_id)
    prompt = ""
    db_prompt = (latest_row or {}).get("prompt_content")
    if isinstance(db_prompt, str) and db_prompt:
        prompt = db_prompt
    elif agent.prompt_path:
        try:
            prompt = agent.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt = ""

    composed_system: str | None = None
    composed_user: str | None = None
    try:
        # Build a duck-typed shim for load_bundle_from_bindings (store: Any)
        _store = types.SimpleNamespace(
            list_prompt_bindings=lambda aid: agent_prompt_resource_bindings.list_for_agent(aid),
            get_repo_resource=lambda rid: resources.get_resource(rid),
            get_active_repo_version=lambda rid: resource_versions.get_active_version(rid),
            get_repo_version=lambda vid: resource_versions.get_version(vid),
            iter_repo_blobs=lambda vid: resource_blobs.iter_blobs(vid),
            get_active_version=lambda aid: agent_versions.get_active(aid),
            latest_version=lambda aid: agent_versions.get_latest(aid),
            list_version_files=lambda vid: agent_version_files.list_for_version(vid),
        )
        bundle = load_bundle_from_bindings(agent_id=agent_id, store=_store)
        if bundle.source is None:
            raise FileNotFoundError("agent has no composition source")
        result = compose_from_source(bundle.source, variables={}, render=False)
        composed_system = result.system
        composed_user = result.user
    except FileNotFoundError:
        logger.info(
            "get_agent_detail: no system slot binding for %r; preview empty",
            agent_id,
        )
    except Exception:
        logger.exception(
            "get_agent_detail: composition preview failed for %r", agent_id
        )

    versions = agent_versions.list_for_agent(agent_id)
    enriched_versions = []
    for v in versions:
        comments = agent_version_comments.list_for_version(v["id"])
        rating = agent_version_ratings.latest_for_version(v["id"])
        enriched_versions.append(
            {
                "id": v["id"],
                "version": v["version"],
                "author": v["author"],
                "changelog": v["changelog"],
                "is_legacy": v["is_legacy"],
                "created_at": v["created_at"],
                "has_comments": len(comments) > 0,
                "rating": rating["rating"] if rating else None,
                "config_json": v.get("config_json"),
            }
        )

    agent_dump = _strip_legacy_runner_model(agent.model_dump())
    bound_profile = EngineService().get_agent_runner_profile(agent_id)
    return {
        "agent": agent_dump,
        "prompt": prompt,
        "composed_system": composed_system,
        "composed_user": composed_user,
        "runner_profile_id": bound_profile.id if bound_profile else None,
        "model": bound_profile.model if bound_profile else None,
        "model_provider": bound_profile.provider if bound_profile else None,
        "workspace": {
            "path": str(workspace_path),
            "ephemeral": ephemeral,
            "generated_configs": {},
        },
        "current_version": latest_row["version"] if latest_row else None,
        "versions": enriched_versions,
        "disabled_at": (agent_meta.get_meta(agent_id) or {}).get("disabled_at"),
    }
