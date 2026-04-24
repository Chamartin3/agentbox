"""Prompt composition — shared bundle renderer for agentbox and callers.

This module is intentionally HTTP-free and side-effect-free so that caller
projects (e.g. cvman) can import it without pulling in the agentbox server
runtime.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _format_template(text: str, variables: dict[str, str]) -> str:
    try:
        return text.format(**variables)
    except KeyError as exc:
        raise KeyError(f"Missing template variable {exc} in prompt") from exc


@dataclass(frozen=True)
class ComposeResult:
    """Result of composing a prompt bundle."""

    system: str
    user: str
    schema: dict[str, Any] | None
    schema_sha: str | None
    bundle_sha: str


def compose(
    bundle_path: Path,
    variables: dict[str, str],
    shared_roots: dict[str, Path],
) -> ComposeResult:
    """Compose a prompt bundle into system + user prompts.

    Args:
        bundle_path: Path to the agent bundle directory.
        variables: Key-value pairs interpolated into templates.
        shared_roots: Mapping of shared root keys to absolute paths.
            Used to resolve ``shared://<key>/...`` references.

    Returns:
        ComposeResult with rendered prompts and metadata.
    """
    bundle_path = bundle_path.resolve()
    agent_toml = bundle_path / "agent.toml"
    if not agent_toml.exists():
        raise FileNotFoundError(f"Bundle missing agent.toml: {bundle_path}")

    with agent_toml.open("rb") as f:
        config = tomllib.load(f)

    composition = config.get("composition")
    if composition is None:
        raise ValueError(f"Bundle {bundle_path} missing [composition] block")

    # -- system prompt -------------------------------------------------
    system_path = bundle_path / composition.get("system_prompt", "prompts/system.md")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_raw = _read_text(system_path)
    system_rendered = _format_template(system_raw, variables)

    # -- references ----------------------------------------------------
    refs = composition.get("references", [])
    ref_parts: list[str] = []
    for ref in refs:
        ref_path_str = ref["path"]
        if ref_path_str.startswith("shared://"):
            rest = ref_path_str[len("shared://") :]
            key, _, rel = rest.partition("/")
            root = shared_roots.get(key)
            if root is None:
                raise ValueError(
                    f"Unknown shared root {key!r} in reference {ref_path_str!r}. "
                    f"Known: {', '.join(sorted(shared_roots))}"
                )
            ref_file = root / rel
        else:
            ref_file = bundle_path / ref_path_str

        if not ref_file.exists():
            raise FileNotFoundError(f"Reference not found: {ref_file}")

        heading = ref.get("heading") or ref_file.stem
        content = _read_text(ref_file)
        ref_parts.append(f"## {heading}\n\n{content}")

    if ref_parts:
        system_rendered = system_rendered + "\n\n" + "\n\n".join(ref_parts)

    # -- user prompt ---------------------------------------------------
    user_template = composition.get("user_template")
    if user_template:
        user_path = bundle_path / user_template
        if not user_path.exists():
            raise FileNotFoundError(f"User template not found: {user_path}")
        user_raw = _read_text(user_path)
        user_rendered = _format_template(user_raw, variables)
    else:
        user_rendered = variables.get("user_message", "")

    # -- output schema -------------------------------------------------
    schema: dict[str, Any] | None = None
    schema_sha: str | None = None
    output_schema_path = composition.get("output_schema")
    if output_schema_path:
        schema_file = bundle_path / output_schema_path
        if not schema_file.exists():
            raise FileNotFoundError(f"Output schema not found: {schema_file}")
        schema = json.loads(_read_text(schema_file))
        schema_sha = _sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")))

    # -- bundle sha ----------------------------------------------------
    # Hash every file we read, in sorted order, as a simple manifest.
    files_to_hash: dict[str, str] = {}
    files_to_hash[str(system_path.relative_to(bundle_path))] = _read_text(system_path)
    if user_template:
        user_path = bundle_path / user_template
        files_to_hash[str(user_path.relative_to(bundle_path))] = _read_text(user_path)
    for ref in refs:
        ref_path_str = ref["path"]
        if ref_path_str.startswith("shared://"):
            rest = ref_path_str[len("shared://") :]
            key, _, rel = rest.partition("/")
            root = shared_roots[key]
            ref_file = root / rel
        else:
            ref_file = bundle_path / ref_path_str
        files_to_hash[ref_path_str] = _read_text(ref_file)
    if output_schema_path:
        schema_file = bundle_path / output_schema_path
        files_to_hash[str(schema_file.relative_to(bundle_path))] = _read_text(
            schema_file
        )

    canonical = "\n".join(
        f"{path}:{content}" for path, content in sorted(files_to_hash.items())
    )
    bundle_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return ComposeResult(
        system=system_rendered,
        user=user_rendered,
        schema=schema,
        schema_sha=schema_sha,
        bundle_sha=bundle_sha,
    )
