"""Bundle sources — decouple the composer from the filesystem.

A ``BundleSource`` is anything that can answer "give me the bytes for this
bundle's system prompt, user template, references, and output schema". The
filesystem implementation is the historical default; the DB implementation
lets a published ``agent_versions`` row render without touching disk.

The composer (``compose_from_source``) consumes whichever source the caller
provides, so the run-time path stays uniform regardless of whether the
agent was resolved from disk or from a versioned snapshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from agentbox.core.constants import BundleFile


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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

    schema: dict[str, Any]
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

    def read_user_template(self) -> str | None:
        """Return the raw user template text, or None when not declared."""

    def read_reference(self, ref: ReferenceSpec) -> str:
        """Return the raw content for a single reference entry."""

    def read_output_schema(self) -> OutputSchemaInfo | None:
        """Return the parsed output schema + its relative path, or None."""

    def read_input_schema(self) -> OutputSchemaInfo | None:
        """Return the parsed input schema + its relative path, or None."""

    def bundle_files(self) -> dict[str, str]:
        """All files consumed, keyed by their bundle-relative identifier.

        Used to compute the bundle_sha so two sources with identical
        contents produce the same digest.
        """


def _normalize_references(raw_refs: list[Any]) -> list[ReferenceSpec]:
    """Coerce the TOML reference list into ``ReferenceSpec`` objects."""
    out: list[ReferenceSpec] = []
    for ref in raw_refs or []:
        if isinstance(ref, dict):
            path = ref.get("path")
            if not isinstance(path, str):
                raise ValueError(f"reference entry missing 'path': {ref!r}")
            heading = ref.get("heading")
            out.append(ReferenceSpec(path=path, heading=heading))
        elif isinstance(ref, str):
            out.append(ReferenceSpec(path=ref))
        else:
            raise ValueError(
                f"reference entry must be string or dict, got {type(ref).__name__}"
            )
    return out


# --------------------------------------------------------------------------- #
# Filesystem
# --------------------------------------------------------------------------- #


@dataclass
class FilesystemBundleSource:
    """Read a bundle from a directory on disk."""

    bundle_path: Path
    composition: dict[str, Any]
    shared_roots: dict[str, Path] = field(default_factory=dict)

    def references(self) -> list[ReferenceSpec]:
        return _normalize_references(self.composition.get("references") or [])

    def read_system(self) -> str:
        rel = self.composition.get("system") or self.composition.get(
            "system_prompt", BundleFile.SYSTEM_PROMPT
        )
        path = self.bundle_path / rel
        if not path.exists():
            raise FileNotFoundError(f"System prompt not found: {path}")
        return _read_text(path)

    def read_user_template(self) -> str | None:
        rel = self.composition.get("user_template")
        if not rel:
            return None
        path = self.bundle_path / rel
        if not path.exists():
            raise FileNotFoundError(f"User template not found: {path}")
        return _read_text(path)

    def _resolve_reference(self, ref: ReferenceSpec) -> Path:
        if ref.path.startswith("shared://"):
            rest = ref.path[len("shared://") :]
            key, _, rel = rest.partition("/")
            root = self.shared_roots.get(key)
            if root is None:
                raise ValueError(
                    f"Unknown shared root {key!r} in reference {ref.path!r}. "
                    f"Known: {', '.join(sorted(self.shared_roots)) or '(none)'}"
                )
            return root / rel
        return self.bundle_path / ref.path

    def read_reference(self, ref: ReferenceSpec) -> str:
        path = self._resolve_reference(ref)
        if not path.exists():
            raise FileNotFoundError(f"Reference not found: {path}")
        return _read_text(path)

    def read_output_schema(self) -> OutputSchemaInfo | None:
        explicit = self.composition.get("output_schema")
        schema_file: Path | None = None
        rel: str | None = None
        if explicit:
            schema_file = self.bundle_path / explicit
            rel = explicit
            if not schema_file.exists():
                raise FileNotFoundError(f"Output schema not found: {schema_file}")
        else:
            for fallback in (BundleFile.OUTPUT_SCHEMA, BundleFile.OUTPUT_SCHEMA_ALT):
                candidate = self.bundle_path / fallback
                if candidate.exists():
                    schema_file = candidate
                    rel = fallback
                    break
        if schema_file is None or rel is None:
            return None
        return OutputSchemaInfo(
            schema=json.loads(_read_text(schema_file)),
            relative_path=rel,
        )

    def read_input_schema(self) -> OutputSchemaInfo | None:
        path = self.bundle_path / BundleFile.INPUT_SCHEMA
        if not path.exists():
            return None
        return OutputSchemaInfo(
            schema=json.loads(_read_text(path)),
            relative_path=BundleFile.INPUT_SCHEMA,
        )

    def bundle_files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        # system
        sys_rel = self.composition.get("system") or self.composition.get(
            "system_prompt", BundleFile.SYSTEM_PROMPT
        )
        files[sys_rel] = (self.bundle_path / sys_rel).read_text(encoding="utf-8")
        # user_template
        user_rel = self.composition.get("user_template")
        if user_rel:
            files[user_rel] = (self.bundle_path / user_rel).read_text(
                encoding="utf-8"
            )
        # references — keyed by the original path string (matches the
        # historical filesystem-only behavior)
        for ref in self.references():
            files[ref.path] = self.read_reference(ref)
        # output schema
        info = self.read_output_schema()
        if info is not None:
            files[info.relative_path] = json.dumps(info.schema, sort_keys=True)
        # input schema
        in_info = self.read_input_schema()
        if in_info is not None:
            files[in_info.relative_path] = json.dumps(in_info.schema, sort_keys=True)
        return files


# --------------------------------------------------------------------------- #
# Database (versioned snapshot)
# --------------------------------------------------------------------------- #


@dataclass
class DbBundleSource:
    """Read a bundle from a versioned snapshot in agent_version_files.

    ``files`` is a list of dicts in the shape returned by
    ``SessionStore.list_version_files()``: each row has ``kind``,
    ``relative_path``, ``content``, ``sha256``, ``source_uri``, ``position``.
    """

    composition: dict[str, Any]
    files: list[dict]

    def __post_init__(self) -> None:
        # Index for fast lookup. References keep their list order via
        # the ``position`` column.
        self._by_kind: dict[str, list[dict]] = {}
        for f in self.files:
            self._by_kind.setdefault(f["kind"], []).append(f)
        for rows in self._by_kind.values():
            rows.sort(key=lambda r: (r.get("position") or 0, r.get("id") or 0))

    def references(self) -> list[ReferenceSpec]:
        # Prefer composition's declared list when present (it preserves
        # `heading`); fall back to the stored rows.
        declared = _normalize_references(self.composition.get("references") or [])
        if declared:
            return declared
        return [
            ReferenceSpec(path=row.get("source_uri") or row["relative_path"])
            for row in self._by_kind.get("reference", [])
        ]

    def _single(self, kind: str) -> dict | None:
        rows = self._by_kind.get(kind) or []
        return rows[0] if rows else None

    def read_system(self) -> str:
        row = self._single("system")
        if row is None:
            raise FileNotFoundError(
                "system prompt missing from DB bundle (no kind='system' row)"
            )
        return row["content"]

    def read_user_template(self) -> str | None:
        # Honor the composition declaration: if user_template is not set,
        # don't return a row even if one exists.
        if not self.composition.get("user_template"):
            return None
        row = self._single("user_template")
        if row is None:
            raise FileNotFoundError(
                "user_template declared in composition but missing from DB bundle"
            )
        return row["content"]

    def read_reference(self, ref: ReferenceSpec) -> str:
        for row in self._by_kind.get("reference", []):
            if row.get("source_uri") == ref.path or row["relative_path"] == ref.path:
                return row["content"]
        raise FileNotFoundError(f"Reference not found in DB bundle: {ref.path!r}")

    def read_output_schema(self) -> OutputSchemaInfo | None:
        row = self._single("output_schema")
        if row is None:
            return None
        rel = row["relative_path"]
        return OutputSchemaInfo(
            schema=json.loads(row["content"]),
            relative_path=rel,
        )

    def read_input_schema(self) -> OutputSchemaInfo | None:
        row = self._single("input_schema")
        if row is None:
            return None
        return OutputSchemaInfo(
            schema=json.loads(row["content"]),
            relative_path=row["relative_path"],
        )

    def bundle_files(self) -> dict[str, str]:
        out: dict[str, str] = {}
        sys_row = self._single("system")
        if sys_row is not None:
            sys_rel = self.composition.get("system") or sys_row["relative_path"]
            out[sys_rel] = sys_row["content"]
        ut_row = self._single("user_template")
        if ut_row is not None and self.composition.get("user_template"):
            out[self.composition["user_template"]] = ut_row["content"]
        for row in self._by_kind.get("reference", []):
            key = row.get("source_uri") or row["relative_path"]
            out[key] = row["content"]
        schema_info = self.read_output_schema()
        if schema_info is not None:
            out[schema_info.relative_path] = json.dumps(
                schema_info.schema, sort_keys=True
            )
        input_info = self.read_input_schema()
        if input_info is not None:
            out[input_info.relative_path] = json.dumps(
                input_info.schema, sort_keys=True
            )
        return out


# --------------------------------------------------------------------------- #
# Bindings (agent_prompt_resource_bindings)
# --------------------------------------------------------------------------- #


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

    The legacy bundle (``DbBundleSource`` / ``FilesystemBundleSource``)
    is no longer consulted. When a slot has no binding, the corresponding
    composition entry is absent (strict — no fallback).
    """

    agent_id: str
    store: Any  # SessionStore — avoid circular import
    composition: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        # Resolve once; downstream methods reuse the same view so we
        # don't re-query for every read_*.
        self._resolved: list[dict] = []
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

        # Strict: every agent must have a system slot binding. Raising
        # here lets the executor's fallback path (filesystem bundle)
        # kick in for un-migrated agents.
        if self._find_slot("system") is None:
            raise FileNotFoundError(
                f"agent {self.agent_id!r} has no slot='system' binding"
            )
        # Synthesize a composition dict so the existing composer
        # branches (which check ``composition['user_template']`` etc.)
        # continue to work without a special case.
        comp: dict[str, Any] = {}
        if self._find_slot("system"):
            comp["system"] = _SYS_PSEUDO
        if self._find_user_template() is not None:
            comp["user_template"] = _USER_PSEUDO
        if self._find_active_slot("input_schema") is not None:
            comp["input_schema"] = _INPUT_SCHEMA_PSEUDO
        if self._find_active_slot("output_schema") is not None:
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

    def _find_slot(self, slot: str) -> dict | None:
        for b in self._resolved:
            if b.get("slot") == slot:
                return b
        return None

    def _find_active_slot(self, slot: str) -> dict | None:
        b = self._find_slot(slot)
        return b if (b and b.get("attach_as_reference")) else None

    def _find_user_template(self) -> dict | None:
        # Slot wins over marker if both exist.
        slot_b = self._find_slot("user_template")
        if slot_b is not None:
            return slot_b
        for b in self._resolved:
            if b.get("marker") == "user_template" and b.get("type") == "document":
                return b
        return None

    def _reference_bindings(self) -> list[dict]:
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

    def _render_blob_text(self, b: dict) -> str:
        # Local import avoids a circular at module import time.
        from agentbox.core.resources.rendering import render_for_type

        rendered = render_for_type(b["type"], b.get("blobs") or [])
        return rendered.get("text") or ""

    def read_system(self) -> str:
        b = self._find_slot("system")
        if b is None:
            raise FileNotFoundError(
                f"agent {self.agent_id!r} has no slot='system' binding"
            )
        return self._render_blob_text(b)

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
        resource_id = ref.path[len(prefix) :]
        for b in self._reference_bindings():
            if b["resource_id"] == resource_id:
                return self._render_blob_text(b)
        raise FileNotFoundError(f"Reference not found in bindings: {ref.path!r}")

    def _read_schema_slot(self, slot: str) -> OutputSchemaInfo | None:
        b = self._find_active_slot(slot)
        if b is None:
            return None
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
                _INPUT_SCHEMA_PSEUDO if slot == "input_schema" else _OUTPUT_SCHEMA_PSEUDO
            ),
        )

    def read_output_schema(self) -> OutputSchemaInfo | None:
        return self._read_schema_slot("output_schema")

    def read_input_schema(self) -> OutputSchemaInfo | None:
        return self._read_schema_slot("input_schema")

    def bundle_files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        sys_b = self._find_slot("system")
        if sys_b is not None:
            files[_SYS_PSEUDO] = self._render_blob_text(sys_b)
        ut_b = self._find_user_template()
        if ut_b is not None:
            files[_USER_PSEUDO] = self._render_blob_text(ut_b)
        for b in self._reference_bindings():
            files[f"bindings://reference/{b['resource_id']}"] = self._render_blob_text(b)
        inp = self._read_schema_slot("input_schema")
        if inp is not None:
            files[_INPUT_SCHEMA_PSEUDO] = json.dumps(inp.schema, sort_keys=True)
        out_ = self._read_schema_slot("output_schema")
        if out_ is not None:
            files[_OUTPUT_SCHEMA_PSEUDO] = json.dumps(out_.schema, sort_keys=True)
        return files
