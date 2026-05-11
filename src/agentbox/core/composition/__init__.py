"""Prompt composition — shared bundle renderer for agentbox and callers.

This module is intentionally HTTP-free and side-effect-free so that caller
projects (e.g. cvman) can import it without pulling in the agentbox server
runtime.

Shared resource references are supported via an optional store parameter:
use ``compose_with_store()`` to resolve ``{shared: "id", version?: n}`` refs.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.composition.sources import (
    BindingsBundleSource,
    BundleSource,
    DbBundleSource,
    FilesystemBundleSource,
)
from agentbox.core.constants import BundleFile

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore


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
_OUTPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "output_schema.md").read_text(encoding="utf-8")
_INPUT_SCHEMA_TEMPLATE = (_PROMPTS_DIR / "input_schema.md").read_text(encoding="utf-8")


def _is_shared_ref(value: Any) -> bool:
    """Check if a value is a shared ref (dict or object with 'shared' key)."""
    if isinstance(value, dict):
        return "shared" in value and isinstance(value.get("shared"), str)
    # Handle Pydantic model
    return hasattr(value, "shared") and isinstance(getattr(value, "shared", None), str)


def _resolve_shared_ref(
    ref: Any, store: SessionStore | None
) -> tuple[str, int | None]:
    """Extract shared id and version from a shared ref.

    Args:
        ref: dict or object with 'shared' and optional 'version' attrs.
        store: SessionStore (unused here, present for future consistency).

    Returns:
        Tuple of (shared_id, version_or_none).

    Raises:
        ValueError: if ref is not a valid shared ref.
    """
    if isinstance(ref, dict):
        shared_id = ref.get("shared")
        if not isinstance(shared_id, str):
            raise ValueError(f"shared ref must have 'shared' key with string value: {ref}")
        version = ref.get("version")
    else:
        shared_id = getattr(ref, "shared", None)
        version = getattr(ref, "version", None)
        if not isinstance(shared_id, str):
            raise ValueError(f"shared ref must have 'shared' attribute with string value: {ref}")
    return (shared_id, version if isinstance(version, int) else None)


def _fetch_shared_content(
    shared_id: str, version: int | None, store: SessionStore, content_type: str = "text"
) -> str | dict[str, Any]:
    """Fetch content from a shared resource.

    Args:
        shared_id: Resource id.
        version: Specific version, or None for active.
        store: SessionStore.
        content_type: 'text' for markdown/plain text, 'json' for schemas.

    Returns:
        String content (text or JSON-dumped schema).

    Raises:
        ValueError: if resource not found or content is None.
    """
    if version is not None:
        record = store.get_resource(shared_id, version)
        if not record:
            raise ValueError(
                f"Shared resource {shared_id!r} version {version} not found"
            )
    else:
        record = store.get_active_resource(shared_id)
        if not record:
            raise ValueError(
                f"Shared resource {shared_id!r} (active) not found"
            )

    if content_type == "json":
        if record.config_json:
            return json.loads(record.config_json)
        elif record.content:
            # Try parsing as JSON if config_json is not set
            try:
                return json.loads(record.content)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Shared resource {shared_id!r} v{record.version} has no "
                    "valid JSON config or content"
                ) from e
        else:
            raise ValueError(
                f"Shared resource {shared_id!r} v{record.version} has no content"
            )
    else:
        # text
        if record.content:
            return record.content
        elif record.config_json:
            # Fall back to JSON for text if content is None
            return record.config_json
        else:
            raise ValueError(
                f"Shared resource {shared_id!r} v{record.version} has no content"
            )


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


def _append_validation_engine_hint(
    text: str, engine: str
) -> str:
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

    if "composition" not in config:
        raise ValueError(
            f"agent.toml at {bundle_path} is missing [composition] block"
        )
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

    # -- input schema --------------------------------------------------
    # Auto-detect input_schema.json at the bundle root and surface it in
    # the system prompt so the agent knows the shape of the user payload.
    input_schema_file = bundle_path / BundleFile.INPUT_SCHEMA
    if input_schema_file.exists():
        try:
            input_schema = json.loads(_read_text(input_schema_file))
        except json.JSONDecodeError:
            input_schema = None
        if input_schema is not None:
            system_rendered = _append_input_schema(system_rendered, input_schema)

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

    Renders system + user + schema from any ``BundleSource`` —
    ``FilesystemBundleSource`` for disk bundles, ``DbBundleSource`` for a
    versioned snapshot pulled from ``agent_version_files``. The two
    sources must yield identical ``ComposeResult`` for the same content
    so a published version reproduces the on-disk run.

    When ``render=False`` template variable substitution is skipped —
    suitable for previews where no run-time variables are available
    (the raw braces and any Jinja-style ``{% %}`` blocks are kept verbatim).
    """
    system_raw = source.read_system()
    system_rendered = _format_template(system_raw, variables) if render else system_raw

    refs = source.references()
    ref_parts: list[str] = []
    for ref in refs:
        content = source.read_reference(ref)
        heading = ref.heading or _ref_heading_fallback(ref.path)
        ref_parts.append(f"## {heading}\n\n{content}")
    if ref_parts:
        system_rendered = system_rendered + "\n\n" + "\n\n".join(ref_parts)

    input_schema_info = source.read_input_schema()
    if input_schema_info is not None:
        system_rendered = _append_input_schema(
            system_rendered, input_schema_info.schema
        )

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
    )


def compose_with_store(
    source: BundleSource,
    variables: dict[str, str],
    *,
    store: SessionStore | None = None,
    render: bool = True,
) -> ComposeResult:
    """Compose a bundle with support for shared resource references.

    Extends ``compose_from_source`` to resolve ``{shared: "id", version?: n}``
    references via the SessionStore. Falls back to ``compose_from_source`` if
    store is None (shared refs will fail if encountered).

    Args:
        source: BundleSource (filesystem or DB).
        variables: Template variable dict.
        store: SessionStore for resolving shared refs (optional).
        render: Whether to perform template variable substitution.

    Returns:
        ComposeResult with rendered prompts and metadata.

    Raises:
        ValueError: if a shared ref cannot be resolved.
    """
    if store is None or not isinstance(source, DbBundleSource):
        return compose_from_source(source, variables, render=render)

    resolved_composition = dict(source.composition)
    resolved_files = list(source.files)

    def _inject(kind: str, shared_id: str, content: str) -> str:
        path = f"shared://{shared_id}"
        resolved_files.append(
            {
                "kind": kind,
                "relative_path": path,
                "content": content,
                "sha256": _sha256(content),
                "source_uri": path,
                "position": len(resolved_files),
            }
        )
        return path

    for slot, kind in (("system", "system"), ("user_template", "user_template")):
        val = resolved_composition.get(slot)
        if _is_shared_ref(val):
            shared_id, version = _resolve_shared_ref(val, store)
            content = _fetch_shared_content(shared_id, version, store, "text")
            resolved_composition[slot] = _inject(kind, shared_id, str(content))

    refs = resolved_composition.get("references") or []
    new_refs: list[Any] = []
    for ref in refs:
        if _is_shared_ref(ref):
            shared_id, version = _resolve_shared_ref(ref, store)
            content = _fetch_shared_content(shared_id, version, store, "text")
            path = _inject("reference", shared_id, str(content))
            new_refs.append(path)
        else:
            new_refs.append(ref)
    resolved_composition["references"] = new_refs

    for slot, kind in (("output_schema", "output_schema"), ("input_schema", "input_schema")):
        val = resolved_composition.get(slot)
        if _is_shared_ref(val):
            shared_id, version = _resolve_shared_ref(val, store)
            obj = _fetch_shared_content(shared_id, version, store, "json")
            content = json.dumps(obj) if isinstance(obj, dict) else str(obj)
            resolved_composition[slot] = _inject(kind, shared_id, content)

    new_source = DbBundleSource(composition=resolved_composition, files=resolved_files)
    return compose_from_source(new_source, variables, render=render)


__all__ = [
    "BindingsBundleSource",
    "BundleSource",
    "ComposeResult",
    "CompositionPreview",
    "DbBundleSource",
    "FilesystemBundleSource",
    "ReferencePreview",
    "compose",
    "compose_from_source",
    "compose_with_store",
    "preview",
]
