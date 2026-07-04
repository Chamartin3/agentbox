"""Resolver and builder functions for agent config."""

from __future__ import annotations

import json as _json
from typing import Any

from agentbox.core.data.payload_types import ConfigJsonPayload, JsonSchemaDict

from agentbox.core.agents.config._types import (
    ExecutionConfig,
    HttpValidatorConfig,
    OutputConfig,
    PythonAgentConfig,
    RuntimeConfig,
    ScriptValidatorConfig,
    ValidatorConfig,
    _config_section,
)


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


def build_config_json_payload(agent: Any) -> ConfigJsonPayload:
    """Project an AgentDef into the structured ``config_json`` payload.

    Used by the backfill migration and by ``create_version`` going
    forward. Mirrors the runtime fallback so a freshly written
    ``config_json`` round-trips identically to the legacy reader.
    """
    exec_cfg = ExecutionConfig.from_agent(agent)
    runtime_cfg = RuntimeConfig.from_agent(agent)
    python_cfg = PythonAgentConfig.from_agent(agent)
    payload: ConfigJsonPayload = {
        "execution": {
            "max_validation_retries": exec_cfg.max_validation_retries,
            "max_error_retries": exec_cfg.max_error_retries,
            "output_validation_engine": exec_cfg.output_validation_engine,
        },
        "runtime": {
            "mcp_config_path": runtime_cfg.mcp_config_path,
            "allowed_tools": list(runtime_cfg.allowed_tools),
        },
        "python": {
            "agent_module": python_cfg.agent_module,
            "deps_factory": python_cfg.deps_factory,
            "output_schema_path": python_cfg.output_schema_path,
        },
    }
    return payload
