"""Preview — read-only snapshot of a bundle composition block."""

from __future__ import annotations
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from agentbox.core.constants import BundleFile
from agentbox.core.agents.composition.bundle._helpers import _read_text

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

