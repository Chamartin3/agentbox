"""Prompt composition — shared bundle renderer for agentbox and callers.

Composes system + user prompts from bundle sources (on-disk or DB-backed),
handles validation, and provides preview snapshots.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, TypedDict

from jsonschema.exceptions import SchemaError

from agentbox.core.agents.composition.schema_io import load_json_schema
from agentbox.core.data.payload_types import JsonSchemaDict
from agentbox.core.data.constants import BundleFile
from agentbox.core.data import CompositionConfig
from agentbox.core.agents.composition.rendering import (
    append_input_schema, append_schema,
)
from agentbox.core.data.composition import (
    ComposedReference,
    ComposeResult,
)
from agentbox.core.agents.composition.rendering import render_for_type

_jsonschema: ModuleType | None
try:
    import jsonschema as _jsonschema
except ImportError:  # pragma: no cover
    _jsonschema = None

logger = logging.getLogger(__name__)


# ── Bundle source protocol ─────────────────────────────────────────


@dataclass(frozen=True)
class ReferenceSpec:
    """One entry of ``[[composition.references]]``.

    ``path`` is the original string from the TOML (``shared://...`` or
    bundle-relative). ``heading`` is the optional section heading; when
    missing, the composer falls back to the file stem.
    """

    path: str
    heading: str | None = None


@dataclass(frozen=True)
class OutputSchemaInfo:
    """Resolved output schema (parsed JSON + the relative path it came from)."""

    schema: JsonSchemaDict
    relative_path: str


class BundleSource(Protocol):
    """Read interface for a single agent bundle.

    Implementations must surface the same ``composition`` dict shape as the
    TOML on disk so the composer can branch on declared fields without
    needing to know the underlying storage.
    """

    composition: dict[str, Any]

    def references(self) -> list[ReferenceSpec]: ...

    def read_system(self) -> str:
        """Return the raw (un-rendered) system prompt text."""
        ...

    def read_user_template(self) -> str | None:
        """Return the raw user template text, or None when not declared."""
        ...

    def read_reference(self, ref: ReferenceSpec) -> str:
        """Return the raw content for a single reference entry."""
        ...

    def read_output_schema(self) -> OutputSchemaInfo | None:
        """Return the parsed output schema + its relative path, or None."""
        ...

    def read_input_schema(self) -> OutputSchemaInfo | None:
        """Return the parsed input schema + its relative path, or None."""
        ...

    def bundle_files(self) -> dict[str, str]:
        """All files consumed, keyed by their bundle-relative identifier.

        Used to compute the bundle_sha so two sources with identical
        contents produce the same digest.
        """
        ...


# ── Helpers ───────────────────────────────────────────────────────


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


def _ref_heading_fallback(path: str) -> str:
    if path.startswith("shared://"):
        tail = path[len("shared://") :].rsplit("/", 1)[-1]
    else:
        tail = path.rsplit("/", 1)[-1]
    stem, _, _ = tail.partition(".")
    return stem or tail


# ── Compose ───────────────────────────────────────────────────────


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
            input_schema = load_json_schema(_read_text(input_schema_file))
        except (json.JSONDecodeError, SchemaError):
            logger.warning(
                "agent input_schema is not a valid JSON Schema; ignoring: %s",
                input_schema_file,
            )
            input_schema = None
        if input_schema is not None:
            system_rendered = append_input_schema(system_rendered, input_schema)

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
        loaded: JsonSchemaDict | None = load_json_schema(_read_text(schema_file))
        schema_sha = _sha256(json.dumps(loaded, sort_keys=True, separators=(",", ":")))
        if isinstance(loaded, dict):
            schema = loaded
            system_rendered = append_schema(system_rendered, schema)

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
        system_rendered = append_input_schema(system_rendered, input_schema)

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
        system_rendered = append_schema(system_rendered, schema)

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


# ── Validation ─────────────────────────────────────────────────────


def validate_input(
    variables: dict[str, str], required: list[str] | None = None
) -> list[str]:
    """Validate that all required variables are present.

    Returns a list of missing variable names (empty if OK).
    """
    required = required or []
    missing = [k for k in required if k not in variables]
    return missing


def precompose_check(
    response: str, schema: dict[str, Any] | None, mode: str = "strict"
) -> tuple[bool, list[str]]:
    """Pre-compose validation of a runner's output against a JSON Schema.

    This is **not** the runtime ``validate_output`` entrypoint — it is a
    composition-time helper for checking bundle output before the run starts.
    Runtime validation lives in ``core.agents.validation.check``.

    Args:
        response: raw output text (expected to be JSON).
        schema: JSON Schema dict (``None`` → auto-pass).
        mode: ``strict`` | ``warn`` | ``off``.

    Returns:
        ``(ok, errors)`` where ``ok`` is ``True`` when validation passes
        or is skipped, and ``errors`` is a list of human-readable messages.
    """
    if mode == "off" or schema is None:
        return True, []

    try:
        instance = json.loads(response)
    except json.JSONDecodeError as exc:
        return False, [f"output is not valid JSON: {exc}"]

    if _jsonschema is None:
        return _basic_shape_check(instance, schema)

    validator = _jsonschema.Draft202012Validator(schema)
    errors = [str(e.message) for e in validator.iter_errors(instance)]
    return len(errors) == 0, errors


def _basic_shape_check(instance: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """Fallback validation when ``jsonschema`` is not installed."""
    errors: list[str] = []
    if not isinstance(instance, dict):
        return False, ["output must be a JSON object"]

    props = schema.get("properties", {})
    required = schema.get("required", [])

    for field_name in required:
        if field_name not in instance:
            errors.append(f"missing required field: {field_name}")
            continue
        field_schema = props.get(field_name, {})
        expected_type = field_schema.get("type")
        if expected_type:
            type_map = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "object": dict,
                "array": list,
            }
            py_type = type_map.get(expected_type)
            if py_type and not isinstance(instance[field_name], py_type):
                errors.append(
                    f"field {field_name!r}: expected {expected_type}, "
                    f"got {type(instance[field_name]).__name__}"
                )
        enum_vals = field_schema.get("enum")
        if enum_vals and instance[field_name] not in enum_vals:
            errors.append(
                f"field {field_name!r}: must be one of {enum_vals}, got {instance[field_name]!r}"
            )

    return len(errors) == 0, errors


# ── BindingsBundleSource ───────────────────────────────────────────


class _ResolvedBinding(TypedDict):
    """Internal shape of a resolved prompt resource binding in memory."""

    binding_id: str
    marker: str | None
    slot: str | None
    attach_as_reference: bool
    resource_id: str
    resource_slug: str
    version_id: str
    content_hash: str
    type: str
    mode: str | None
    display_name: str
    display_order: int
    required: bool
    blobs: list[Any]  # ResourceBlobRow instances from iter_repo_blobs


# Pseudo paths used in the synthesized ``composition`` dict so the rest
# of the composer (which still treats the composition as a TOML-shaped
# document with file paths) does not need to special-case bindings.
_SYS_PSEUDO = "bindings://system"
_USER_PSEUDO = "bindings://user_template"
_INPUT_SCHEMA_PSEUDO = "bindings://input_schema"
_OUTPUT_SCHEMA_PSEUDO = "bindings://output_schema"


@dataclass
class BindingsBundleSource:
    """Read a bundle from ``agent_prompt_resource_bindings``.

    All composition inputs come from bindings:

    * ``slot='system'``         → system prompt
    * ``slot='user_template'``  → user template (or marker='user_template')
    * ``slot='input_schema'``   → input schema (gated on attach_as_reference)
    * ``slot='output_schema'``  → output schema (gated on attach_as_reference)
    * marker bindings with ``attach_as_reference=True`` → references

    When a slot has no binding, the corresponding composition entry is
    absent (strict — no fallback to disk).
    """

    agent_id: str
    store: Any  # duck-typed store (RunStore) — avoid circular import
    composition: dict[str, Any] = field(init=False)

    # Files attached to the active agent_version row (relative_path → content).
    # Populated when falling back to ``agent_versions`` for the system prompt
    # so the composer can read schemas declared in agent.toml's
    # ``[composition].output_schema`` / ``input_schema`` paths without
    # requiring an explicit slot binding.
    _av_files: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        # Resolve once; downstream methods reuse the same view so we
        # don't re-query for every read_*.
        self._resolved: list[_ResolvedBinding] = []
        bindings = self.store.list_prompt_bindings(self.agent_id)
        for b in bindings:
            resource = self.store.get_repo_resource(b["resource_id"])
            if resource is None:
                continue
            version_id = b.get("pinned_version_id")
            if not version_id:
                active = self.store.get_active_repo_version(b["resource_id"])
                if not active:
                    continue
                version_id = active["id"]
            version = self.store.get_repo_version(version_id)
            blobs = list(self.store.iter_repo_blobs(version_id))
            self._resolved.append(
                {
                    "binding_id": b["id"],
                    "marker": b.get("marker"),
                    "slot": b.get("slot"),
                    "attach_as_reference": bool(b.get("attach_as_reference")),
                    "resource_id": b["resource_id"],
                    "resource_slug": resource["slug"],
                    "version_id": version_id,
                    "content_hash": version["content_hash"],
                    "type": resource["type"],
                    "mode": b.get("mode"),
                    "display_name": resource["display_name"],
                    "display_order": b.get("display_order", 0),
                    "required": bool(b.get("required", 1)),
                    "blobs": blobs,
                }
            )

        # DB-as-source-of-truth: ``agent_versions.prompt_content`` is the
        # only runtime source of the system prompt. Legacy
        # ``slot='system'`` bindings are ignored — they remain in the
        # table for history but never feed the composer. This guarantees
        # every ``edit_prompt`` call reaches the runner.
        self._av_prompt: str | None = None
        self._av_config: dict[str, Any] = {}
        av = None
        try:
            av = self.store.get_active_version(self.agent_id)
        except Exception:
            av = None
        if av is None:
            try:
                av = self.store.latest_version(self.agent_id)
            except Exception:
                av = None
        prompt = (av or {}).get("prompt_content") if isinstance(av, dict) else None
        if not prompt:
            raise ValueError(
                f"agent {self.agent_id!r} has no agent_versions.prompt_content. "
                "Populate it via the UI prompt editor or "
                "agentbox-mcp.edit_prompt."
            )
        self._av_prompt = prompt
        cfg = (av or {}).get("config_json") if isinstance(av, dict) else None
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except (ValueError, TypeError):
                cfg = None
        if isinstance(cfg, dict):
            self._av_config = cfg

        try:
            version_id = av.get("id") if isinstance(av, dict) else None
            if version_id is not None:
                self._av_files = {
                    row["relative_path"]: row["content"]
                    for row in self.store.list_version_files(version_id)
                    if row.get("relative_path")
                }
        except Exception:
            self._av_files = {}

        # Synthesize a composition dict so the existing composer
        # branches (which check ``composition['user_template']`` etc.)
        # continue to work without a special case.
        comp: dict[str, Any] = {}
        if self._av_prompt is not None:
            comp["system"] = _SYS_PSEUDO
        if self._find_user_template() is not None:
            comp["user_template"] = _USER_PSEUDO
        if (
            self._find_active_slot("input_schema") is not None
            or self._av_schema_path("input_schema") is not None
        ):
            comp["input_schema"] = _INPUT_SCHEMA_PSEUDO
        if (
            self._find_active_slot("output_schema") is not None
            or self._av_schema_path("output_schema") is not None
        ):
            comp["output_schema"] = _OUTPUT_SCHEMA_PSEUDO
        comp["references"] = [
            {
                "path": f"bindings://reference/{b['resource_id']}",
                "heading": b.get("display_name") or b.get("resource_slug"),
            }
            for b in self._reference_bindings()
        ]
        self.composition = comp

    # --- internal lookup helpers ---

    def _find_slot(self, slot: str) -> _ResolvedBinding | None:
        for b in self._resolved:
            if b.get("slot") == slot:
                return b
        return None

    def _find_active_slot(self, slot: str) -> _ResolvedBinding | None:
        b = self._find_slot(slot)
        return b if (b and b.get("attach_as_reference")) else None

    def _find_user_template(self) -> _ResolvedBinding | None:
        # Slot wins over marker if both exist.
        slot_b = self._find_slot("user_template")
        if slot_b is not None:
            return slot_b
        for b in self._resolved:
            if b.get("marker") == "user_template" and b.get("type") == "document":
                return b
        return None

    def _reference_bindings(self) -> list[_ResolvedBinding]:
        refs = [
            b
            for b in self._resolved
            if b.get("attach_as_reference")
            and not b.get("slot")
            and b.get("marker") != "user_template"
            and b.get("type") in ("document", "folder", "skill")
        ]
        refs.sort(key=lambda b: b.get("display_order", 0))
        return refs

    # --- BundleSource protocol ---

    def references(self) -> list[ReferenceSpec]:
        return [
            ReferenceSpec(
                path=f"bindings://reference/{b['resource_id']}",
                heading=b.get("display_name") or b.get("resource_slug"),
            )
            for b in self._reference_bindings()
        ]

    def _render_blob_text(self, b: _ResolvedBinding) -> str:
        rendered = render_for_type(b["type"], b.get("blobs") or [])
        return rendered.get("text") or ""

    def read_system(self) -> str:
        # DB-as-source-of-truth: always ``agent_versions.prompt_content``.
        # Any ``slot='system'`` binding is ignored (history only).
        if self._av_prompt is None:
            raise FileNotFoundError(
                f"agent {self.agent_id!r} has no agent_versions.prompt_content"
            )
        return self._av_prompt

    def read_user_template(self) -> str | None:
        b = self._find_user_template()
        if b is None:
            return None
        return self._render_blob_text(b)

    def read_reference(self, ref: ReferenceSpec) -> str:
        # The composition uses bindings:// paths so the binding id maps
        # back to a resource_id directly.
        prefix = "bindings://reference/"
        if not ref.path.startswith(prefix):
            raise FileNotFoundError(
                f"BindingsBundleSource cannot resolve non-binding reference {ref.path!r}"
            )
        resource_id = ref.path[len(prefix):]
        for b in self._reference_bindings():
            if b["resource_id"] == resource_id:
                return self._render_blob_text(b)
        raise FileNotFoundError(f"Reference not found in bindings: {ref.path!r}")

    def _av_schema_path(self, slot: str) -> str | None:
        """Return the schema path declared in the agent_version's
        composition snapshot (TOML-shaped), when the schema file is also
        present in ``agent_version_files``. Acts as the DB-side analogue
        of reading ``output_schema.json`` from the bundle on disk."""
        comp = (
            self._av_config.get("composition")
            if isinstance(self._av_config, dict)
            else None
        )
        if not isinstance(comp, dict):
            return None
        path = comp.get(slot)
        if not isinstance(path, str) or not path:
            return None
        return path if path in self._av_files else None

    def _read_schema_slot(self, slot: str) -> OutputSchemaInfo | None:
        b = self._find_active_slot(slot)
        if b is None:
            path = self._av_schema_path(slot)
            if path is None:
                return None
            text = self._av_files[path]
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"agent {self.agent_id!r} {slot} file {path!r} is not valid JSON: {exc}"
                ) from exc
            return OutputSchemaInfo(
                schema=parsed,
                relative_path=(
                    _INPUT_SCHEMA_PSEUDO
                    if slot == "input_schema"
                    else _OUTPUT_SCHEMA_PSEUDO
                ),
            )
        text = self._render_blob_text(b)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"agent {self.agent_id!r} {slot} binding content is not valid JSON: {exc}"
            ) from exc
        return OutputSchemaInfo(
            schema=parsed,
            relative_path=(
                _INPUT_SCHEMA_PSEUDO
                if slot == "input_schema"
                else _OUTPUT_SCHEMA_PSEUDO
            ),
        )

    def read_output_schema(self) -> OutputSchemaInfo | None:
        return self._read_schema_slot("output_schema")

    def read_input_schema(self) -> OutputSchemaInfo | None:
        return self._read_schema_slot("input_schema")

    def bundle_files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        if self._av_prompt is not None:
            files[_SYS_PSEUDO] = self._av_prompt
        ut_b = self._find_user_template()
        if ut_b is not None:
            files[_USER_PSEUDO] = self._render_blob_text(ut_b)
        for b in self._reference_bindings():
            files[f"bindings://reference/{b['resource_id']}"] = self._render_blob_text(
                b
            )
        inp = self._read_schema_slot("input_schema")
        if inp is not None:
            files[_INPUT_SCHEMA_PSEUDO] = json.dumps(inp.schema, sort_keys=True)
        out_ = self._read_schema_slot("output_schema")
        if out_ is not None:
            files[_OUTPUT_SCHEMA_PSEUDO] = json.dumps(out_.schema, sort_keys=True)
        return files


# ── Bundle Loader ──────────────────────────────────────────────────


@dataclass
class Bundle:
    """Self-contained agent bundle ready for composition.

    DB-backed only: carries a ``BundleSource`` built from
    ``agent_prompt_resource_bindings``. ``path`` is retained for
    backward-compatible introspection but is always ``None`` at runtime.
    """

    agent_id: str
    path: Path | None = None
    composition: CompositionConfig | None = None
    source: BundleSource | None = None

    def compose(
        self,
        variables: dict[str, str],
        shared_roots: dict[str, Path] | None = None,
    ) -> ComposeResult:
        if self.source is None:
            raise ValueError(f"Bundle for {self.agent_id!r} has no source")
        return compose_from_source(self.source, variables)


def load_bundle_from_bindings(
    agent_id: str,
    store: Any,
) -> Bundle:
    """Build a Bundle backed by agent_prompt_resource_bindings.

    DB-as-source-of-truth: composition state comes from bindings, with a
    fallback to ``agent_versions.prompt_content`` when no slot='system'
    binding exists. The on-disk bundle is never consulted at runtime.
    """
    source = BindingsBundleSource(agent_id=agent_id, store=store)
    # Synthesize a CompositionConfig from the source's composition dict so
    # downstream callers that introspect ``bundle.composition`` keep
    # working. Unknown fields are dropped by model_validate.
    composition = CompositionConfig.model_validate(source.composition)
    return Bundle(
        agent_id=agent_id,
        path=None,
        composition=composition,
        source=source,
    )


__all__ = [
    "BundleSource",
    "ReferenceSpec",
    "OutputSchemaInfo",
    "compose",
    "compose_from_source",
    "ComposeResult",
    "ComposedReference",
    "validate_input",
    "precompose_check",
    "BindingsBundleSource",
    "Bundle",
    "load_bundle_from_bindings",
]
