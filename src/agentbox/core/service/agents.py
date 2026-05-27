"""Shared agent-resolution service used by both REST and MCP surfaces.

The DB (``agent_versions`` / ``active_agent_versions``) is the single
source of truth. There is no manifest fallback — the deprecated disk
loader does not participate in agent resolution.

In addition to the low-level ``resolve_agent`` / ``list_all_agents``
helpers, this module exposes two higher-level read views consumed by
the ``/api/agents`` routes (and re-usable by MCP / CLI):

* :func:`list_agents_enriched` — list view with run counts, last-run
  timestamps, and the bound runner profile resolved.
* :func:`get_agent_detail` — single-agent view used by ``GET
  /api/agents/{id}``, including the composed prompt preview, the
  active prompt body, versions, and workspace info.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import func, select

from agentbox.core import workspaces as ws
from agentbox.core.agent.config import build_config_json_payload
from agentbox.core.constants import SessionMode
from agentbox.core.data import AgentDef, agent_runner_profiles
from agentbox.core.data import runs as runs_table
from agentbox.core.prompt.composition import compose_from_source
from agentbox.core.prompt.composition.loader import load_bundle_from_bindings

if TYPE_CHECKING:
    from agentbox.config import Settings
    from agentbox.core.data import SessionStore

logger = logging.getLogger(__name__)


def resolve_agent(
    agent_id: str,
    *,
    store: SessionStore,
    loader: Any = None,
) -> AgentDef | None:
    """Return the ``AgentDef`` for ``agent_id`` from the DB, or ``None``.

    ``loader`` is accepted for backward compatibility with call sites that
    still thread it; it is ignored. Disk-only agents must be imported into
    the DB before they can be resolved.
    """
    del loader  # deprecated, ignored
    return store.get_agent_def(agent_id)


def list_all_agents(
    *,
    store: SessionStore,
    loader: Any = None,
) -> list[AgentDef]:
    """Return every known agent from the DB (latest snapshot per id).

    Snapshot rows that fail validation are skipped with a warning so a
    single bad row never blanks the whole list. ``loader`` is accepted
    for backward compatibility and ignored.
    """
    del loader  # deprecated, ignored
    out: list[AgentDef] = []
    for row in store.list_agents_with_latest():
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
    """Two cheap queries for run counts / last-run / profile bindings.

    Wrapped in a broad try so a single bad row in either table never
    blanks the agents list — the caller falls back to empty dicts.
    """
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
    """Drop the legacy ``runner.model`` cosmetic field.

    The bound runner profile is the runtime source of truth; ``model``
    and ``model_provider`` are surfaced at the top level instead.
    """
    if isinstance(dumped.get("runner"), dict):
        dumped["runner"] = {
            k: v for k, v in dumped["runner"].items() if k != "model"
        }
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
    return data


def list_agents_enriched(
    *,
    store: SessionStore,
    settings: Settings,
) -> list[dict]:
    """List view used by ``GET /api/agents``.

    Combines :func:`list_all_agents` with run-count aggregation and
    bound runner-profile resolution, returning plain dicts suitable
    for JSON serialization.
    """
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
        for agent in list_all_agents(store=store)
    ]


def get_agent_detail(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict | None:
    """Detail view used by ``GET /api/agents/{agent_id}``.

    Returns ``None`` when the agent is unknown. The returned dict
    includes the active prompt body, a composed system+user preview,
    bound runner profile, workspace info, and the full version list.
    """
    agent = resolve_agent(agent_id, store=store)
    if agent is None:
        return None
    workspace_path, ephemeral = ws.resolve_path(agent, settings, store)

    latest_row = store.get_active_version(agent_id) or store.latest_version(agent_id)
    # DB is source of truth — surface the active version's prompt_content;
    # only fall back to the on-disk prompt_path file when the DB row has no
    # stored content (legacy / unmigrated agents).
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
    }


# ---------------------------------------------------------------------------
# Agent creation + version file management
# ---------------------------------------------------------------------------


class AgentAlreadyExists(ValueError):
    """Raised when create_agent_record is called for an existing agent_id."""


class VersionNotFound(LookupError):
    pass


class VersionNotDraft(ValueError):
    pass


class DuplicateVersionFile(ValueError):
    """Same sha256 or relative_path already attached to the draft version."""


class VersionFileNotFound(LookupError):
    pass


def create_agent_record(
    *,
    store: SessionStore,
    agent_id: str,
    description: str,
    runner: Any,
    prompt: str | None,
    composition: Any,
    tools: list[str] | None,
    tags: list[str] | None,
    workspace: Any,
    session_mode: Any,
    webhook_url: str | None,
    author: str,
    changelog: str,
) -> dict:
    """Create a v1 draft agent in the DB and return the version record.

    Raises :class:`AgentAlreadyExists` when the agent_id is already taken.
    """
    agent_def = AgentDef(
        id=agent_id,
        description=description,
        runner=runner,
        prompt=prompt,
        composition=composition,
        tools=tools or [],
        tags=tags or [],
        workspace=workspace,
        session_mode=cast(SessionMode, session_mode or "headless"),
        webhook_url=webhook_url,
        source_path=None,
        source_format=None,
    )
    try:
        return store.create_agent(
            agent_id=agent_id,
            config_json={
                **agent_def.model_dump(mode="json", exclude_none=True),
                **build_config_json_payload(agent_def),
            },
            prompt_content=prompt,
            author=author,
            changelog=changelog,
            source="ui",
            source_path=None,
            source_format=None,
            sync_mode="off",
            export_to_disk=False,
        )
    except ValueError as exc:
        raise AgentAlreadyExists(str(exc)) from exc


def upload_version_file(
    *,
    store: SessionStore,
    agent_id: str,
    version: int,
    kind: str,
    name: str,
    content: str,
) -> dict:
    """Attach a file to a draft version. Returns the inserted file row.

    Raises :class:`VersionNotFound`, :class:`VersionNotDraft`, or
    :class:`DuplicateVersionFile`.
    """
    version_record = store.get_version(agent_id, version)
    if version_record is None:
        raise VersionNotFound(f"version {version} not found")
    if not version_record.get("is_draft"):
        raise VersionNotDraft("cannot modify published version")

    sha256_hash = hashlib.sha256(content.encode()).hexdigest()
    files = store.list_version_files(version_record["id"])
    for f in files:
        if f.get("sha256") == sha256_hash:
            raise DuplicateVersionFile("duplicate_sha256")
        if f.get("relative_path") == name:
            raise DuplicateVersionFile("duplicate_path")

    store.insert_version_files(
        version_record["id"],
        [
            {
                "relative_path": name,
                "kind": kind,
                "content": content,
                "sha256": sha256_hash,
            }
        ],
    )
    files = store.list_version_files(version_record["id"])
    inserted = next((f for f in files if f.get("sha256") == sha256_hash), None)
    if inserted is None:
        raise RuntimeError("file_insert_failed")
    return {"file": inserted, "sha256": sha256_hash, "size": len(content)}


def delete_version_file(
    *,
    store: SessionStore,
    agent_id: str,
    version: int,
    file_id: int,
) -> None:
    """Detach a file from a draft version.

    Raises :class:`VersionNotFound`, :class:`VersionNotDraft`, or
    :class:`VersionFileNotFound`.
    """
    version_record = store.get_version(agent_id, version)
    if version_record is None:
        raise VersionNotFound(f"version {version} not found")
    if not version_record.get("is_draft"):
        raise VersionNotDraft("not_draft")
    files = store.list_version_files(version_record["id"])
    if not any(f.get("id") == file_id for f in files):
        raise VersionFileNotFound(f"file {file_id} not found")
    store.delete_version_file(file_id)


class AgentNotFound(LookupError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"unknown agent {agent_id!r}")
        self.agent_id = agent_id


def require_agent_exists(
    agent_id: str, *, store: SessionStore, loader: Any = None
) -> None:
    """Raise :class:`AgentNotFound` unless ``agent_id`` resolves in store or loader.

    Mirrors the legacy "store-or-loader" probe still required by the
    /api/agents/.../versions routes for agents imported before the DB
    became authoritative.
    """
    if store.get_agent_def(agent_id) is not None:
        return
    if loader is not None and loader.get(agent_id) is not None:
        return
    raise AgentNotFound(agent_id)
