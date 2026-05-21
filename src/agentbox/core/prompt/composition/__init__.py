"""Prompt composition — shared bundle renderer for agentbox and callers.

This module is intentionally HTTP-free and side-effect-free so that caller
projects can import it without pulling in the agentbox server
runtime.

"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox.core.constants import BundleFile
from agentbox.core.prompt.composition.sources import (
    BindingsBundleSource,
    BundleSource,
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_TEMPLATE_VAR_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _format_template(text: str, variables: dict[str, str]) -> str:
    """Substitute ``{var_name}`` placeholders only.

    Unlike ``str.format``, this leaves every other brace untouched — so
    prompts can embed literal JSON examples (``{"key": value}``) without
    needing them escaped as ``{{ }}``. Only bare identifier placeholders
    matching a known variable key are replaced; unknown ``{name}`` tokens
    are passed through verbatim.
    """
    missing: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        missing.append(key)
        return m.group(0)

    rendered = _TEMPLATE_VAR_RE.sub(_sub, text)
    if missing:
        raise KeyError(f"Missing template variable {missing[0]!r} in prompt")
    return rendered


_PROMPTS_DIR = Path(__file__).parent / "prompts"
_OUTPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "output_schema.md").read_text(
    encoding="utf-8"
)
_INPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "input_schema.md").read_text(encoding="utf-8")


def _append_input_schema(text: str, schema: dict[str, Any]) -> str:
    """Append an input-format instruction block describing ``schema``.

    Goes on the system prompt so the agent learns the shape of the
    incoming payload up-front, before the user message is processed.
    """
    block = _INPUT_SCHEMA_TEMPLATE.format(schema=json.dumps(schema, indent=2)).rstrip()
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def _append_schema(text: str, schema: dict[str, Any]) -> str:
    """Append a structured-output instruction block referencing ``schema``.

    Agents that declare an output_schema expect their final reply to be a
    single JSON object conforming to that schema. The schema block is
    appended to the system prompt (the durable contract), not the user
    message — that keeps the contract co-located with the agent's role
    instructions and out of the variable user input.

    The instruction text lives in ``prompts/output_schema.md`` so it can be
    edited without code changes.
    """
    block = _OUTPUT_SCHEMA_TEMPLATE.format(schema=json.dumps(schema, indent=2)).rstrip()
    base = (text or "").rstrip()
    return f"{base}\n\n{block}" if base else block


def _append_validation_engine_hint(text: str, engine: str) -> str:
    """Append a short note about which validation engine will be enforced.

    This tells the LLM how strictly its output will be checked so it can
    self-correct before emitting.
    """
    hints = {
        "jsonschema": (
            "## Validation\n\nYour output will be validated against the schema "
            "above using JSON Schema. All required fields must be present and "
            "types must match."
        ),
        "pydantic": (
            "## Validation\n\nYour output will be validated using strict "
            "type checking (pydantic). Required fields, string lengths, and "
            "type constraints are enforced — missing or malformed fields will "
            "cause the run to fail."
        ),
        "both": (
            "## Validation\n\nYour output will be validated twice: first "
            "against the JSON Schema above, then through strict type checking "
            "(pydantic). Required fields, string lengths, type constraints, "
            "and structural rules are all enforced — any violation causes "
            "the run to fail."
        ),
    }
    hint = hints.get(engine, hints["both"])
    base = (text or "").rstrip()
    return f"{base}\n\n{hint}" if base else hint


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
    schema: dict[str, Any] | None
    schema_sha: str | None
    bundle_sha: str
    system_base: str = ""
    references: tuple[ComposedReference, ...] = ()
    input_schema: dict[str, Any] | None = None


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


def _ref_heading_fallback(path: str) -> str:
    if path.startswith("shared://"):
        tail = path[len("shared://") :].rsplit("/", 1)[-1]
    else:
        tail = path.rsplit("/", 1)[-1]
    stem, _, _ = tail.partition(".")
    return stem or tail


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
    input_schema: dict[str, Any] | None = None
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
    schema: dict[str, Any] | None = None
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


__all__ = [
    "BindingsBundleSource",
    "BundleSource",
    "ComposeResult",
    "ComposedReference",
    "CompositionPreview",
    "ReferencePreview",
    "compose",
    "compose_from_source",
    "preview",
]
