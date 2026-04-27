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
