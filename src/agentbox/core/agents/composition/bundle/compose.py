"""Compose — bundle composition into system + user prompts."""

from __future__ import annotations
import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from agentbox.core.data.payload_types import JsonSchemaDict
from agentbox.core.data.constants import BundleFile
from agentbox.core.agents.composition.bundle._helpers import (
    _append_input_schema, _append_schema, _format_template,
    _read_text, _ref_heading_fallback, _sha256,
)
from agentbox.core.agents.composition.bundle.sources import BundleSource

@dataclass(frozen=True)
class ComposedReference:
    """One reference section as composed (raw, rendered text)."""

    path: str
    heading: str
    content: str


@dataclass(frozen=True)
class ComposeResult:
    """Result of composing a prompt bundle.

    ``system`` is the fully-composed system prompt (base + input schema
    block + references + output schema block) — what file-based backends
    (claude_code, opencode, codex, pi) need.

    ``system_base`` is the raw rendered system prompt **without** the
    auto-appended schema/reference blocks. The token backend uses this
    because pydantic-ai injects its own schema description and the
    reference content goes via deps; appending the schema again would
    duplicate (and potentially conflict with) what pydantic-ai sends.

    ``references`` and ``input_schema`` are likewise the structured
    pieces, available so backends can route them to native channels
    instead of string-concatenation.
    """

    system: str
    user: str
    schema: JsonSchemaDict | None
    schema_sha: str | None
    bundle_sha: str
    system_base: str = ""
    references: tuple[ComposedReference, ...] = ()
    input_schema: JsonSchemaDict | None = None


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

    if "composition" not in config:
        raise ValueError(f"agent.toml at {bundle_path} is missing [composition] block")
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

    # -- input schema --------------------------------------------------
    # Auto-detect input_schema.json at the bundle root and surface it in
    # the system prompt so the agent knows the shape of the user payload.
    # Placed before references so the agent learns the payload shape up-front.
    input_schema_file = bundle_path / BundleFile.INPUT_SCHEMA
    if input_schema_file.exists():
        try:
            input_schema = json.loads(_read_text(input_schema_file))
        except json.JSONDecodeError:
            input_schema = None
        if input_schema is not None:
            system_rendered = _append_input_schema(system_rendered, input_schema)

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
    schema: JsonSchemaDict | None = None
    schema_sha: str | None = None
    output_schema_path = composition.get("output_schema")
    schema_file: Path | None = None
    if output_schema_path:
        explicit_schema_file = bundle_path / output_schema_path
        if not explicit_schema_file.exists():
            raise FileNotFoundError(f"Output schema not found: {explicit_schema_file}")
        schema_file = explicit_schema_file
    else:
        for fallback in (BundleFile.OUTPUT_SCHEMA, BundleFile.OUTPUT_SCHEMA_ALT):
            candidate = bundle_path / fallback
            if candidate.exists():
                schema_file = candidate
                output_schema_path = fallback
                break
    if schema_file is not None:
        loaded: JsonSchemaDict | None = json.loads(_read_text(schema_file))
        schema_sha = _sha256(json.dumps(loaded, sort_keys=True, separators=(",", ":")))
        if isinstance(loaded, dict):
            schema = loaded
            system_rendered = _append_schema(system_rendered, schema)

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


def compose_from_source(
    source: BundleSource,
    variables: dict[str, str],
    *,
    render: bool = True,
) -> ComposeResult:
    """Storage-agnostic composer.

    Renders system + user + schema from any ``BundleSource`` — currently
    ``BindingsBundleSource`` (agent_prompt_resource_bindings is the
    single source of truth post-bundle deprecation).

    When ``render=False`` template variable substitution is skipped —
    suitable for previews where no run-time variables are available
    (the raw braces and any Jinja-style ``{% %}`` blocks are kept verbatim).
    """
    system_raw = source.read_system()
    system_base = _format_template(system_raw, variables) if render else system_raw

    # Build the "full" composed system for backends that send everything as
    # a single prompt string. ``system_base`` stays clean for backends that
    # have native channels for schemas/references (token → pydantic-ai).
    system_rendered = system_base

    input_schema_info = source.read_input_schema()
    input_schema: JsonSchemaDict | None = None
    if input_schema_info is not None:
        input_schema = input_schema_info.schema
        system_rendered = _append_input_schema(system_rendered, input_schema)

    refs = source.references()
    composed_refs: list[ComposedReference] = []
    ref_parts: list[str] = []
    for ref in refs:
        content = source.read_reference(ref)
        heading = ref.heading or _ref_heading_fallback(ref.path)
        composed_refs.append(
            ComposedReference(path=ref.path, heading=heading, content=content)
        )
        ref_parts.append(f"## {heading}\n\n{content}")
    if ref_parts:
        system_rendered = system_rendered + "\n\n" + "\n\n".join(ref_parts)

    user_template = source.read_user_template()
    if user_template is not None:
        user_rendered = (
            _format_template(user_template, variables) if render else user_template
        )
    else:
        user_rendered = variables.get("user_message", "") if render else ""

    schema_info = source.read_output_schema()
    schema: JsonSchemaDict | None = None
    schema_sha: str | None = None
    if schema_info is not None:
        schema = schema_info.schema
        schema_sha = _sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")))
        system_rendered = _append_schema(system_rendered, schema)

    files_to_hash = source.bundle_files()
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
        system_base=system_base,
        references=tuple(composed_refs),
        input_schema=input_schema,
    )
