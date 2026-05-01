"""TOML write helpers for standalone and legacy-dir agent formats.

Extracted from manifest_writer.py to keep that module under 400 lines.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Table

from agentbox.core.data.manifest import AgentDef, RunnerSpec, SharedRef


def _serialize_composition_ref(value: Any) -> str | dict | Table:
    """Serialize a single composition value (str or SharedRef/dict) for TOML output.

    Parameters
    ----------
    value:
        A string (file path), a SharedRef instance, or a dict with ``shared`` key.

    Returns
    -------
    str | dict | Table:
        - Plain string → returned as-is.
        - SharedRef instance or dict with ``shared`` → tomlkit inline table.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, SharedRef):
        t = tomlkit.inline_table()
        t["shared"] = value.shared
        if value.version is not None:
            t["version"] = value.version
        return t
    if isinstance(value, dict) and "shared" in value:
        t = tomlkit.inline_table()
        t["shared"] = value["shared"]
        if "version" in value and value["version"] is not None:
            t["version"] = value["version"]
        return t
    return value


def _build_composition_table(agent: AgentDef) -> Table | None:
    """Build a [composition] table for an agent if composition is set.

    Returns None if agent has no composition.
    """
    comp = agent.composition
    if not comp:
        return None

    ct: Table = tomlkit.table()

    # system prompt
    ct["system"] = _serialize_composition_ref(comp.system)

    # references (list of paths or shared refs)
    if comp.references:
        refs_arr = tomlkit.array()
        for ref in comp.references:
            refs_arr.append(_serialize_composition_ref(ref))
        ct["references"] = refs_arr

    # user_template
    if comp.user_template:
        ct["user_template"] = _serialize_composition_ref(comp.user_template)

    # input_schema
    if comp.input_schema:
        ct["input_schema"] = _serialize_composition_ref(comp.input_schema)

    # output_schema
    if comp.output_schema:
        ct["output_schema"] = _serialize_composition_ref(comp.output_schema)

    # transport (non-default)
    if comp.transport != "system_message":
        ct["transport"] = comp.transport

    # output_validation (non-default)
    if comp.output_validation != "strict":
        ct["output_validation"] = comp.output_validation

    return ct


def _build_runner_table(r: RunnerSpec) -> Table:
    """Convert a ``RunnerSpec`` to a tomlkit ``Table`` of non-default fields."""
    rt: Table = tomlkit.table()
    if r.model:
        rt["model"] = r.model
    if r.timeout_seconds != 120:
        rt["timeout_seconds"] = r.timeout_seconds
    if r.mcp_config_path:
        rt["mcp_config_path"] = r.mcp_config_path
    if r.allowed_tools:
        arr = tomlkit.array()
        arr.extend(r.allowed_tools)
        rt["allowed_tools"] = arr
    if r.extra_args:
        arr = tomlkit.array()
        arr.extend(r.extra_args)
        rt["extra_args"] = arr
    if r.agent_module:
        rt["agent_module"] = r.agent_module
    if r.output_schema_path:
        rt["output_schema_path"] = r.output_schema_path
    if r.max_validation_retries:
        rt["max_validation_retries"] = r.max_validation_retries
    return rt


def write_standalone_toml(path: Path, agent: AgentDef) -> None:
    """Write a standalone ``.toml`` file for an agent."""
    doc = tomlkit.document()
    doc["id"] = agent.id
    if agent.description:
        doc["description"] = agent.description
    if agent.workspace:
        doc["workspace"] = agent.workspace
    if agent.tools:
        arr = tomlkit.array()
        arr.extend(agent.tools)
        doc["tools"] = arr
    if agent.tags:
        arr = tomlkit.array()
        arr.extend(agent.tags)
        doc["tags"] = arr
    if agent.session_mode != "headless":
        doc["session_mode"] = agent.session_mode
    if not agent.claude_agent:
        doc["claude_agent"] = False
    if agent.headless:
        doc["headless"] = True
    if agent.webhook_url:
        doc["webhook_url"] = agent.webhook_url
    if agent.unsupported_backends:
        arr = tomlkit.array()
        arr.extend(agent.unsupported_backends)
        doc["unsupported_backends"] = arr

    # Composition takes precedence over prompt/prompt_path
    comp_table = _build_composition_table(agent)
    if comp_table:
        doc["composition"] = comp_table
    elif agent.prompt:
        doc["prompt"] = agent.prompt
    elif agent.prompt_path:
        doc["prompt_path"] = agent.prompt_path

    rt = _build_runner_table(agent.runner)
    doc["runner"] = rt

    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, tomlkit.dumps(doc))


def write_legacy_dir(agent_dir: Path, agent: AgentDef) -> None:
    """Write the legacy agent.toml + prompts/system.md format.

    When composition is set, it takes precedence over prompt_path/prompt.
    """
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = agent_dir / "agent.toml"
    doc = tomlkit.document()
    doc["id"] = agent.id
    if agent.description:
        doc["description"] = agent.description
    if agent.workspace:
        doc["workspace"] = agent.workspace
    if agent.tools:
        arr = tomlkit.array()
        arr.extend(agent.tools)
        doc["tools"] = arr
    if agent.tags:
        arr = tomlkit.array()
        arr.extend(agent.tags)
        doc["tags"] = arr
    if agent.session_mode != "headless":
        doc["session_mode"] = agent.session_mode
    if agent.webhook_url:
        doc["webhook_url"] = agent.webhook_url

    # Composition takes precedence
    comp_table = _build_composition_table(agent)
    if comp_table:
        doc["composition"] = comp_table
    else:
        doc["prompt_path"] = "prompts/system.md"

    rt = _build_runner_table(agent.runner)
    if rt:
        doc["runner"] = rt

    _atomic_write(manifest_path, tomlkit.dumps(doc))

    if agent.prompt and not agent.composition:
        # Only write prompt file if no composition is set
        prompts_dir = agent_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(prompts_dir / "system.md", agent.prompt)


def _atomic_write(path: Path, text: str) -> None:
    # Write the tmp file next to the target so os.replace() stays on the
    # same filesystem (cross-device replace raises OSError 18 on bind mounts).
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except PermissionError:
        # Parent directory isn't writable (e.g. single-file bind mount
        # where the dir is root-owned).  Fall back to direct overwrite.
        path.write_text(text, encoding="utf-8")
    except OSError:
        # Fall back to a system tmp dir + copy when the target dir is read-only.
        sys_tmp = Path(tempfile.gettempdir()) / f"{path.name}.tmp"
        sys_tmp.write_text(text, encoding="utf-8")
        try:
            path.write_text(text, encoding="utf-8")
        finally:
            sys_tmp.unlink(missing_ok=True)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
