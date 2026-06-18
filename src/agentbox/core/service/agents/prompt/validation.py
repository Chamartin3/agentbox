"""Agent validation config management.

Handles validator normalization, ``get_agent_validation``, and
``put_agent_validation``.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
from typing import Any

from agentbox.core.agents.composition.drift import (
    _build_snapshot,
)
from agentbox.core.constants import ValidatorKind
from agentbox.core.db import SessionStore
from agentbox.core.service.agents.crud import resolve_agent
from agentbox.core.service.agents.prompt.patch import (
    AgentServiceError,
    decode_config_json,
)

logger = logging.getLogger(__name__)


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
        try:
            ValidatorKind.coerce(kind, label="validator kind")
        except ValueError:
            raise AgentServiceError(
                400,
                "invalid_validator",
                (
                    f"{direction}.validators[{i}].kind={kind!r} — must be "
                    f"one of {ValidatorKind.values()}. The jsonschema validator is "
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
        try:
            ValidatorKind.coerce(entry.get("kind", ""), label="validator kind")
        except ValueError:
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
