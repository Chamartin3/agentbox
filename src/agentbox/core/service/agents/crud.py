"""Agent CRUD + enriched read views — extracted from __init__.py per C10.

Import from ``service.agents`` (the package), never from this module directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from agentbox.core import workspaces as ws
from agentbox.core.agents.composition.bundle import compose_from_source
from agentbox.core.agents.composition.bundle.loader import load_bundle_from_bindings
from agentbox.core.db import AgentDef, agent_runner_profiles
from agentbox.core.db import runs as runs_table

if TYPE_CHECKING:
    from agentbox.core.config import Settings
    from agentbox.core.db import SessionStore

logger = logging.getLogger(__name__)


def resolve_agent(
    agent_id: str,
    *,
    store: SessionStore,
) -> AgentDef | None:
    return store.get_agent_def(agent_id)


def list_all_agents(
    *,
    store: SessionStore,
    include_disabled: bool = False,
) -> list[AgentDef]:
    out: list[AgentDef] = []
    for row in store.list_agents_with_latest(include_disabled=include_disabled):
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
    store: SessionStore,
) -> tuple[dict[str, int], dict[str, str], dict[str, str]]:
    run_counts: dict[str, int] = {}
    last_run_at: dict[str, str] = {}
    profile_bindings: dict[str, str] = {}
    try:
        with store.engine.connect() as conn:
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
    store: SessionStore,
    settings: Settings,
    run_counts: dict[str, int],
    last_run_at: dict[str, str],
    profile_bindings: dict[str, str],
) -> dict:
    try:
        workspace_str = str(ws.resolve_path(agent, settings, store)[0])
    except Exception:
        workspace_str = ""
    active = store.get_active_version(agent.id)
    latest = store.latest_version(agent.id)
    dumped = _strip_legacy_runner_model(agent.model_dump())
    profile_id = profile_bindings.get(agent.id)
    profile = store.get_runner_profile(profile_id) if profile_id else None
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
    meta = store.get_agent_meta(agent.id) or {}
    data["disabled_at"] = meta.get("disabled_at")
    return data


def list_agents_enriched(
    *,
    store: SessionStore,
    settings: Settings,
    include_disabled: bool = False,
) -> list[dict]:
    run_counts, last_run_at, profile_bindings = _aggregate_run_metadata(store)
    return [
        _enrich_agent(
            agent,
            store=store,
            settings=settings,
            run_counts=run_counts,
            last_run_at=last_run_at,
            profile_bindings=profile_bindings,
        )
        for agent in list_all_agents(store=store, include_disabled=include_disabled)
    ]


def get_agent_detail(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict | None:
    agent = resolve_agent(agent_id, store=store)
    if agent is None:
        return None
    workspace_path, ephemeral = ws.resolve_path(agent, settings, store)

    latest_row = store.get_active_version(agent_id) or store.latest_version(agent_id)
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
        bundle = load_bundle_from_bindings(agent_id=agent_id, store=store)
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

    versions = store.list_versions(agent_id)
    enriched_versions = []
    for v in versions:
        comments = store.list_comments(v["id"])
        rating = store.get_rating(v["id"])
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
    bound_profile = store.get_agent_runner_profile(agent_id)
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
        "disabled_at": (store.get_agent_meta(agent_id) or {}).get("disabled_at"),
    }
