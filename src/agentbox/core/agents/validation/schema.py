"""Schema resolution and output contract configuration.

Pulled from ``validation/schema.py``, ``config/_types.py`` (OutputConfig),
and ``config/_helpers.py`` (resolve_output_config).
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox.core.agents.definition import PythonAgentConfig
from agentbox.core.data.composition import (
    HttpValidatorConfig,
    ScriptValidatorConfig,
    ValidatorConfig,
)
from agentbox.core.data.payload_types import JsonSchemaDict


def resolve_schema(
    agent: Any,
    workdir: Path,
    project_root: Path | None = None,
    composed_schema: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Locate the agent's output schema.

    Returns ``(schema_dict, error_msg)`` — ``schema_dict`` is ``None`` when
    no schema is configured (caller should treat the run as no-validation),
    or when the schema file is missing/unreadable (caller should surface
    ``error_msg`` as a validation failure).

    Resolution order:
      1. ``composed_schema`` (already-rendered binding from the prompt
         composer / output-schema prompt-binding).
      2. ``python.output_schema_path`` (legacy file-based contract).
    """
    if isinstance(composed_schema, dict):
        return composed_schema, ""

    python_cfg = PythonAgentConfig.from_agent(agent)
    schema_rel = python_cfg.output_schema_path
    if not schema_rel:
        return None, ""

    schema_path = workdir / schema_rel
    if not schema_path.exists() and project_root is not None:
        schema_path = project_root / schema_rel
    if not schema_path.exists():
        return None, f"schema file not found: {schema_rel}"

    try:
        return _json.loads(schema_path.read_text(encoding="utf-8")), ""
    except (_json.JSONDecodeError, OSError) as exc:
        return None, f"cannot load schema: {exc}"


@dataclass(frozen=True)
class OutputConfig:
    """Resolved output validation surface for a single run.

    Two independent pieces:

    - ``json_schema`` — Gate-1 structural validation. Sourced from the
      agent's ``slot='output_schema'`` resource binding. Its existence
      *is* the implicit jsonschema validator — never listed in
      ``validators``.
    - ``validators`` — explicit polymorphic post-hoc checkers from the
      bound validation contract. Each validator carries its own
      ``description`` (rendered into the prompt as a constraint bullet)
      and the actual check (HTTP endpoint, script resource, …). Today
      ``kind='http'`` and ``kind='script'``; new kinds add a dispatch
      branch in ``core/run/validation.check_output`` with no DB
      migration.
    """

    json_schema: JsonSchemaDict | None = None
    validators: tuple[ValidatorConfig, ...] = ()


def _normalize_validator_entries(
    store: Any, entries: list[dict]
) -> list[ValidatorConfig]:
    """Turn raw validator dicts (from inline config_json or a contract
    row) into typed :class:`ValidatorConfig`s.

    Script validators pre-load their source code so the runtime needs
    no DB access during dispatch. Unknown kinds are skipped silently —
    a newer writer may have introduced a kind this reader doesn't know.
    """
    out: list[ValidatorConfig] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind", "http")
        description = str(entry.get("description", "") or "")
        if kind == "http":
            out.append(
                HttpValidatorConfig(
                    kind="http",
                    endpoint=entry.get("endpoint", ""),
                    timeout_seconds=int(entry.get("timeout_seconds", 5)),
                    description=description,
                )
            )
        elif kind == "script":
            rid = entry.get("resource_id")
            if not rid:
                continue
            pinned = entry.get("pinned_version_id")
            ver = None
            if store is not None:
                try:
                    if pinned:
                        ver = store.get_repo_version(pinned)
                    else:
                        ver = store.get_active_repo_version(rid)
                except Exception:
                    ver = None
            source = ""
            if ver and store is not None:
                try:
                    blob = store.read_repo_blob(ver["id"], "")
                except Exception:
                    blob = None
                if blob:
                    text = blob.get("content_text") or ""
                    if not text:
                        raw_b = blob.get("content")
                        if isinstance(raw_b, (bytes, bytearray)):
                            try:
                                text = raw_b.decode("utf-8")
                            except UnicodeDecodeError:
                                text = ""
                    source = text
            out.append(
                ScriptValidatorConfig(
                    kind="script",
                    resource_id=rid,
                    resource_version_id=(ver or {}).get("id"),
                    source_code=source,
                    description=description,
                )
            )
    return out


def _config_section(agent: Any, section: str) -> dict[str, Any]:
    """Return the ``config_json[section]`` dict for an agent, if any.

    AgentDef itself doesn't carry config_json — it's a column on
    ``agent_versions``. Some call sites already attach the active row
    via ``agent.__dict__["_config_json"]`` after a DB load. Honour
    that when present; otherwise return an empty dict.
    """
    raw = agent.__dict__.get("_config_json") if hasattr(agent, "__dict__") else None
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except (ValueError, TypeError):
            return {}
    if not isinstance(raw, dict):
        return {}
    sub = raw.get(section)
    return sub if isinstance(sub, dict) else {}


def resolve_output_config(store: Any, agent: Any) -> OutputConfig:
    """Resolve the agent's output contract — single source of truth.

    Two independent reads:

    1. **Schema** — from the agent's active ``slot='output_schema'``
       prompt binding (resolved blob of the pinned-or-active version).
    2. **Validators** — inline ``config_json["output"].validators`` on
       the active agent_version.

    Either may be absent.
    """
    agent_id = getattr(agent, "id", None)
    schema: JsonSchemaDict | None = None
    validators_raw: list[dict] = []

    if store is not None and agent_id:
        # --- schema from output_schema binding ---
        try:
            bindings = store.list_prompt_bindings(agent_id)
        except Exception:
            bindings = []
        binding = next((b for b in bindings if b.get("slot") == "output_schema"), None)
        if binding is not None:
            vid = binding.get("pinned_version_id")
            try:
                if vid:
                    ver = store.get_repo_version(vid)
                else:
                    ver = store.get_active_repo_version(binding["resource_id"])
            except Exception:
                ver = None
            if ver:
                try:
                    blob = store.read_repo_blob(ver["id"], "")
                except Exception:
                    blob = None
                if blob:
                    text = blob.get("content_text")
                    if not text:
                        raw_b = blob.get("content")
                        if isinstance(raw_b, (bytes, bytearray)):
                            try:
                                text = raw_b.decode("utf-8")
                            except UnicodeDecodeError:
                                text = None
                    if isinstance(text, str) and text:
                        try:
                            schema = _json.loads(text)
                        except (ValueError, TypeError):
                            schema = None

        # --- validators from inline config_json["output"].validators ---
        inline_section = _config_section(agent, "output")
        inline_list = inline_section.get("validators")
        if isinstance(inline_list, list):
            validators_raw = [v for v in inline_list if isinstance(v, dict)]

    validators = (
        _normalize_validator_entries(store, validators_raw) if validators_raw else []
    )

    typed_schema: JsonSchemaDict | None = schema if isinstance(schema, dict) else None
    return OutputConfig(
        json_schema=typed_schema,
        validators=tuple(validators),
    )


__all__ = ["OutputConfig", "resolve_output_config", "resolve_schema"]
