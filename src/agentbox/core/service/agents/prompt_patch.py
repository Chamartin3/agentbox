"""Agent config patching.

Handles ``patch_agent_config`` and its supporting helpers.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
from typing import Any

from agentbox.core.agents import (
    build_agent_snapshot,
    build_config_json_str,
)
from agentbox.core.agents import engine_load_failure as backend_load_failure
from agentbox.core.agents import list_engines
from agentbox.core.data import AgentDef
from agentbox.core.data._util import now_iso
from agentbox.core.db import (
    ActiveAgentVersionManager,
    AgentDefManager,
    AgentSyncManager,
    AgentVersionManager,
)
from agentbox.core.service.agents.crud import resolve_agent

logger = logging.getLogger(__name__)

_FORBIDDEN_PATCH_KEYS = {"id"}


class AgentServiceError(Exception):
    def __init__(self, status_code: int, code: str, detail: Any) -> None:
        super().__init__(f"{code}: {detail}")
        self.status_code = status_code
        self.code = code
        self.detail = detail


def decode_config_json(raw: Any) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _apply_patch_to_agent(agent_dump: dict, patch: dict) -> dict:
    out = dict(agent_dump)
    for k, v in patch.items():
        if k in _FORBIDDEN_PATCH_KEYS:
            continue
        if k == "runner" and isinstance(v, dict):
            base = dict(out.get("runner") or {})
            base.update({rk: rv for rk, rv in v.items() if rv is not None})
            out["runner"] = base
        elif k == "composition" and isinstance(v, dict):
            base = dict(out.get("composition") or {})
            base.update({ck: cv for ck, cv in v.items() if cv is not None})
            out["composition"] = base
        else:
            out[k] = v
    return out


def _validate_runner_against_registry(agent: AgentDef) -> None:
    kind = agent.runner.kind
    name = kind
    loaded = list_engines()
    if name in loaded:
        return
    failure = backend_load_failure(name)
    if failure is not None:
        raise AgentServiceError(
            400,
            "backend_unloadable",
            (
                f"runner.kind={name!r} is declared but failed to load "
                f"at startup ({failure})."
            ),
        )
    raise AgentServiceError(
        400,
        "backend_unknown",
        (
            f"runner.kind={name!r} has no backend installed. "
            f"Registered: {sorted(loaded.keys())}."
        ),
    )


def patch_agent_config(
    *,
    agent_defs: AgentDefManager,
    agent_versions: AgentVersionManager,
    active_agent_versions: ActiveAgentVersionManager,
    agent_sync: AgentSyncManager,
    settings: Any,
    agent_id: str,
    patch: dict,
) -> AgentDef:
    if not patch:
        raise AgentServiceError(400, "empty_patch", "empty patch")

    current = resolve_agent(agent_id, agent_defs=agent_defs)
    if current is None:
        raise AgentServiceError(404, "unknown_agent", agent_id)

    merged = _apply_patch_to_agent(current.model_dump(mode="python"), patch)
    try:
        updated = AgentDef.model_validate(merged)
    except Exception as exc:
        raise AgentServiceError(400, "validation_failed", str(exc)) from exc
    _validate_runner_against_registry(updated)
    updated.source_path = current.source_path
    updated.source_format = current.source_format

    prompt_text = ""
    if updated.prompt_path:
        try:
            prompt_text = updated.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""
    snapshot = build_agent_snapshot(updated)
    config_json = build_config_json_str(updated)

    active_row = agent_versions.get_active(agent_id)

    prior_cfg = decode_config_json((active_row or {}).get("config_json"))
    new_cfg = _json.loads(config_json)
    for direction in ("input", "output"):
        prior_section = prior_cfg.get(direction)
        if not isinstance(prior_section, dict) or "validators" not in prior_section:
            continue
        section = new_cfg.get(direction)
        if not isinstance(section, dict):
            section = {}
        section.setdefault("validators", prior_section["validators"])
        new_cfg[direction] = section
    config_json = _json.dumps(new_cfg)

    carried_prompt_content = (
        (active_row or {}).get("prompt_content") or prompt_text or None
    )
    carried_prompt_snapshot = (
        prompt_text or (active_row or {}).get("prompt_snapshot") or ""
    )

    try:
        vid = agent_versions.insert_version(
            agent_id=updated.id,
            version=agent_versions.next_version(updated.id),
            source_path=str(updated.source_path) if updated.source_path else "",
            source_format=(
                updated.source_format.value if updated.source_format else "unknown"
            ),
            content_snapshot=snapshot,
            prompt_snapshot=carried_prompt_snapshot,
            content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            author="api:patch",
            changelog=f"patch: {', '.join(sorted(patch))}",
            config_json=config_json,
            prompt_content=carried_prompt_content,
            is_legacy=0,
            created_at=now_iso(),
            source="api",
        )
        new_version = agent_versions.get_by_id(vid)
        assert new_version is not None
    except Exception as exc:
        logger.exception("patch_agent_config: DB write failed for %r", agent_id)
        raise AgentServiceError(500, "db_write_failed", agent_id) from exc

    try:
        active_agent_versions.set_pointer(updated.id, int(new_version["id"]), now_iso())
    except Exception as exc:
        logger.exception(
            "patch_agent_config: activate_version failed for %r", agent_id
        )
        raise AgentServiceError(500, "activate_failed", agent_id) from exc

    # upsert_agent_sync
    now = now_iso()
    proxy_path = str(updated.source_path) if updated.source_path else None
    if agent_sync.get_row(updated.id) is None:
        agent_sync.insert(
            agent_id=updated.id,
            proxy_path=proxy_path,
            sync_mode="manual",
            sync_policy="db_wins",
            last_file_hash=None,
            last_file_mtime=None,
            last_sync_at=now,
        )
    else:
        patch_values: dict = {"last_sync_at": now}
        if proxy_path is not None:
            patch_values["proxy_path"] = proxy_path
        agent_sync.patch(updated.id, **patch_values)

    return updated
