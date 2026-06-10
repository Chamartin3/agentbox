"""Agent config patching + validation — extracted from __init__.py per C10.

Import from ``service.agents`` (the package), never from this module directly.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
from typing import Any

from agentbox.core.agents.composition.drift import (
    _build_config_json,
    _build_snapshot,
)
from agentbox.core.agents.resolve import engine_load_failure as backend_load_failure
from agentbox.core.agents.resolve import list_engines
from agentbox.core.data import AgentDef, SessionStore

from agentbox.core.service.agents.crud import resolve_agent

logger = logging.getLogger(__name__)

VALID_VALIDATOR_KINDS = ("http", "script")
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
    name = kind.value if hasattr(kind, "value") else str(kind)
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
    store: SessionStore,
    settings: Any,
    agent_id: str,
    patch: dict,
) -> AgentDef:
    if not patch:
        raise AgentServiceError(400, "empty_patch", "empty patch")

    current = resolve_agent(agent_id, store=store)
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
    snapshot = _build_snapshot(updated)
    config_json = _build_config_json(updated)

    active_row = store.get_active_version(agent_id)

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
        new_version = store.create_version(
            agent_id=updated.id,
            source_path=str(updated.source_path) if updated.source_path else "",
            source_format=(
                updated.source_format.value if updated.source_format else "unknown"
            ),
            content_snapshot=snapshot,
            prompt_snapshot=carried_prompt_snapshot,
            content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            author="api:patch",
            changelog=f"patch: {', '.join(sorted(patch))}",
            files=None,
            config_json=config_json,
            prompt_content=carried_prompt_content,
        )
    except Exception as exc:
        logger.exception("patch_agent_config: DB write failed for %r", agent_id)
        raise AgentServiceError(500, "db_write_failed", agent_id) from exc

    try:
        store.activate_version(updated.id, int(new_version["id"]))
    except Exception as exc:
        logger.exception(
            "patch_agent_config: activate_version failed for %r", agent_id
        )
        raise AgentServiceError(500, "activate_failed", agent_id) from exc

    store.upsert_agent_sync(
        agent_id=updated.id,
        proxy_path=str(updated.source_path) if updated.source_path else None,
    )

    return updated


def normalize_validator_entries(direction: str, entries: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise AgentServiceError(
                400,
                "invalid_validator",
                f"{direction}.validators[{i}] must be an object",
            )
        kind = entry.get("kind", "http")
        if kind not in VALID_VALIDATOR_KINDS:
            raise AgentServiceError(
                400,
                "invalid_validator",
                (
                    f"{direction}.validators[{i}].kind={kind!r} — must be "
                    f"one of {VALID_VALIDATOR_KINDS}. The jsonschema validator is "
                    "implicit from the schema binding and must not be "
                    "listed here."
                ),
            )
        desc = entry.get("description", "") or ""
        if not isinstance(desc, str):
            raise AgentServiceError(
                400,
                "invalid_validator",
                f"{direction}.validators[{i}].description must be a string",
            )
        if kind == "http":
            endpoint = entry.get("endpoint")
            if not isinstance(endpoint, str) or not endpoint:
                raise AgentServiceError(
                    400,
                    "invalid_validator",
                    f"{direction}.validators[{i}]: http requires a non-empty endpoint",
                )
            out.append(
                {
                    "kind": "http",
                    "endpoint": endpoint,
                    "timeout_seconds": int(entry.get("timeout_seconds", 5)),
                    "description": desc,
                }
            )
        else:  # script
            rid = entry.get("resource_id")
            if not isinstance(rid, str) or not rid:
                raise AgentServiceError(
                    400,
                    "invalid_validator",
                    (
                        f"{direction}.validators[{i}]: script requires "
                        "resource_id (pointing at a repo_resource of type='script')"
                    ),
                )
            pinned = entry.get("pinned_version_id")
            if pinned is not None and not isinstance(pinned, str):
                raise AgentServiceError(
                    400,
                    "invalid_validator",
                    (
                        f"{direction}.validators[{i}]: script.pinned_version_id "
                        "must be a string or null"
                    ),
                )
            row: dict = {"kind": "script", "resource_id": rid, "description": desc}
            if pinned:
                row["pinned_version_id"] = pinned
            out.append(row)
    return out


def _validators_view(cfg: dict, direction: str) -> dict | None:
    section = cfg.get(direction)
    if not isinstance(section, dict):
        return None
    entries = section.get("validators")
    if not isinstance(entries, list) or not entries:
        return None
    cleaned: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") not in VALID_VALIDATOR_KINDS:
            continue
        cleaned.append(dict(entry))
    if not cleaned:
        return None
    return {"validators": cleaned}


def get_agent_validation(store: SessionStore, agent_id: str) -> dict:
    active = store.get_active_version(agent_id)
    if not active or active.get("id") is None:
        return {
            "agent_id": agent_id,
            "agent_version_id": None,
            "input": None,
            "output": None,
        }
    cfg = decode_config_json(active.get("config_json"))
    return {
        "agent_id": agent_id,
        "agent_version_id": int(active["id"]),
        "input": _validators_view(cfg, "input"),
        "output": _validators_view(cfg, "output"),
    }


def put_agent_validation(
    *,
    store: SessionStore,
    settings: Any,
    agent_id: str,
    input_validators: list[dict] | None,
    output_validators: list[dict] | None,
    reason: str,
    actor: str | None,
) -> dict:
    current = resolve_agent(agent_id, store=store)
    if current is None:
        raise AgentServiceError(404, "unknown_agent", agent_id)

    explicit: dict[str, list[dict]] = {}
    if input_validators is not None:
        explicit["input"] = normalize_validator_entries("input", input_validators)
    if output_validators is not None:
        explicit["output"] = normalize_validator_entries("output", output_validators)
    if not explicit:
        raise AgentServiceError(
            400, "empty_validation_patch", "supply input and/or output"
        )

    active = store.get_active_version(current.id) or {}
    base_cfg = decode_config_json(active.get("config_json"))
    for direction, validators in explicit.items():
        section = base_cfg.get(direction)
        if not isinstance(section, dict):
            section = {}
        section["validators"] = validators
        base_cfg[direction] = section
    new_config_json = _json.dumps(base_cfg)

    prompt_text = ""
    if current.prompt_path:
        try:
            prompt_text = current.load_prompt(settings.project_root)
        except FileNotFoundError:
            prompt_text = ""
    snapshot = _build_snapshot(current)
    carried_prompt_content = (
        active.get("prompt_content")
        or (current.prompt or "").strip()
        or prompt_text
        or None
    )

    try:
        new_version = store.create_version(
            agent_id=current.id,
            source_path=str(current.source_path) if current.source_path else "",
            source_format=(
                current.source_format.value if current.source_format else "unknown"
            ),
            content_snapshot=snapshot,
            prompt_snapshot=prompt_text,
            content_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
            author=actor or "api:validation",
            changelog=f"validation: {reason}",
            files=None,
            config_json=new_config_json,
            prompt_content=carried_prompt_content,
        )
    except Exception as exc:
        logger.exception("put_agent_validation: create_version failed for %r", agent_id)
        raise AgentServiceError(500, "db_write_failed", agent_id) from exc

    try:
        store.activate_version(current.id, int(new_version["id"]))
    except Exception as exc:
        logger.exception(
            "put_agent_validation: activate_version failed for %r", agent_id
        )
        raise AgentServiceError(500, "activate_failed", agent_id) from exc

    return get_agent_validation(store, agent_id)
