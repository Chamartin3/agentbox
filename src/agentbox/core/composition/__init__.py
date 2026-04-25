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

from agentbox.core.constants import BundleFile


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _format_template(text: str, variables: dict[str, str]) -> str:
    try:
        return text.format(**variables)
    except KeyError as exc:
        raise KeyError(f"Missing template variable {exc} in prompt") from exc


_PROMPTS_DIR = Path(__file__).parent / "prompts"
_OUTPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "output_schema.md").read_text(encoding="utf-8")


def _append_schema_to_user(user_text: str, schema: dict[str, Any]) -> str:
    """Append a structured-output instruction block referencing ``schema``.

    Agents that declare an output_schema expect their final reply to be a
    single JSON object conforming to that schema. Surfacing the schema in
    the user message — rather than relying on per-bundle prompt prose —
    keeps the contract in one place (the Pydantic-derived JSON Schema)
    and prevents drift between validators and prompts.

    The instruction text lives in ``prompts/output_schema.md`` so it can be
    edited without code changes.
    """
    block = _OUTPUT_SCHEMA_TEMPLATE.format(schema=json.dumps(schema, indent=2)).rstrip()
    base = (user_text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


@dataclass(frozen=True)
class ComposeResult:
    """Result of composing a prompt bundle."""

    system: str
    user: str
    schema: dict[str, Any] | None
    schema_sha: str | None
    bundle_sha: str


@dataclass(frozen=True)
class ReferencePreview:
    """One reference file as exposed in a composition preview."""

    path: str
    heading: str
    content: str


@dataclass(frozen=True)
class CompositionPreview:
    """Read-only snapshot of a bundle's [composition] block.

    Unlike ``compose()``, this returns raw file contents without template
    substitution — suitable for showing the user what the bundle declares.
    """

    system: str
    user_template: str | None
    references: list[ReferencePreview]
    output_schema: dict[str, Any] | None
    input_schema: dict[str, Any] | None = None


def preview(
    bundle_path: Path,
    shared_roots: dict[str, Path],
) -> CompositionPreview:
    """Load a bundle's [composition] block as raw, un-rendered content.

    Args:
        bundle_path: Path to the agent bundle directory.
        shared_roots: Mapping of shared root keys to absolute paths for
            resolving ``shared://<key>/...`` reference paths.

    Returns:
        ``CompositionPreview`` with raw system markdown, raw user template
        (if any), each reference's content, and the output schema JSON
        (if the bundle declares ``output_schema``).
    """
    bundle_path = bundle_path.resolve()
    agent_toml = bundle_path / "agent.toml"
    if not agent_toml.exists():
        raise FileNotFoundError(f"Bundle missing agent.toml: {bundle_path}")
    with agent_toml.open("rb") as f:
        config = tomllib.load(f)
    composition = config.get("composition") or {}

    system_rel = composition.get("system") or composition.get(
        "system_prompt", BundleFile.SYSTEM_PROMPT
    )
    system_path = bundle_path / system_rel
    system_text = _read_text(system_path) if system_path.exists() else ""

    user_template_rel = composition.get("user_template")
    user_template_text: str | None = None
    if user_template_rel:
        user_path = bundle_path / user_template_rel
        if user_path.exists():
            user_template_text = _read_text(user_path)

    refs: list[ReferencePreview] = []
    for ref in composition.get("references", []):
        ref_path_str = ref["path"] if isinstance(ref, dict) else str(ref)
        if ref_path_str.startswith("shared://"):
            rest = ref_path_str[len("shared://") :]
            key, _, rel = rest.partition("/")
            root = shared_roots.get(key)
            if root is None:
                continue
            ref_file = root / rel
        else:
            ref_file = bundle_path / ref_path_str
        if not ref_file.exists():
            continue
        heading = (
            ref.get("heading") if isinstance(ref, dict) and ref.get("heading") else None
        ) or ref_file.stem
        refs.append(
            ReferencePreview(
                path=ref_path_str,
                heading=heading,
                content=_read_text(ref_file),
            )
        )

    schema: dict[str, Any] | None = None
    output_schema_rel = composition.get("output_schema")
    schema_file: Path | None = None
    if output_schema_rel:
        schema_file = bundle_path / output_schema_rel
    else:
        for sibling_name in (BundleFile.OUTPUT_SCHEMA, BundleFile.OUTPUT_SCHEMA_ALT):
            sibling = bundle_path / sibling_name
            if sibling.exists():
                schema_file = sibling
                break
    if schema_file is not None and schema_file.exists():
        try:
            schema = json.loads(_read_text(schema_file))
        except json.JSONDecodeError:
            schema = None

    input_schema: dict[str, Any] | None = None
    input_schema_file = bundle_path / BundleFile.INPUT_SCHEMA
    if input_schema_file.exists():
        try:
            input_schema = json.loads(_read_text(input_schema_file))
        except json.JSONDecodeError:
            input_schema = None

    return CompositionPreview(
        system=system_text,
        user_template=user_template_text,
        references=refs,
        output_schema=schema,
        input_schema=input_schema,
    )


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

    composition = config.get("composition") or {}

    # -- system prompt -------------------------------------------------
    system_rel = composition.get("system") or composition.get(
        "system_prompt", BundleFile.SYSTEM_PROMPT
    )
    system_path = bundle_path / system_rel
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
    # Resolve from explicit [composition].output_schema, or auto-detect
    # output_schema.json / schema.json at the bundle root so agents get
    # structured-output instructions without per-bundle wiring.
    schema: dict[str, Any] | None = None
    schema_sha: str | None = None
    output_schema_path = composition.get("output_schema")
    schema_file: Path | None = None
    if output_schema_path:
        schema_file = bundle_path / output_schema_path
        if not schema_file.exists():
            raise FileNotFoundError(f"Output schema not found: {schema_file}")
    else:
        for fallback in (BundleFile.OUTPUT_SCHEMA, BundleFile.OUTPUT_SCHEMA_ALT):
            candidate = bundle_path / fallback
            if candidate.exists():
                schema_file = candidate
                output_schema_path = fallback
                break
    if schema_file is not None:
        schema = json.loads(_read_text(schema_file))
        schema_sha = _sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")))
        user_rendered = _append_schema_to_user(user_rendered, schema)

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
    if schema_file is not None:
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
