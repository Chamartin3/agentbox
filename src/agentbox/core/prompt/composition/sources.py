"""Bundle sources — decouple the composer from the storage backend.

A ``BundleSource`` is anything that can answer "give me the bytes for this
bundle's system prompt, user template, references, and output schema".
``BindingsBundleSource`` is the only implementation: it reads from
``agent_prompt_resource_bindings``, which is the single source of truth
post-bundle deprecation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


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

    When a slot has no binding, the corresponding composition entry is
    absent (strict — no fallback to disk).
    """

    agent_id: str
    store: Any  # SessionStore — avoid circular import
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

        # DB-as-source-of-truth: when no slot='system' binding exists,
        # fall back to ``agent_versions.prompt_content`` (the active
        # version row). Bindings exist for shared/cross-agent prompts;
        # simple agents whose prompt lives in their own version row
        # should not need a binding to run. Disk fallback removed in
        # Plan 18 — bundles are never read from the filesystem at
        # runtime.
        self._av_prompt: str | None = None
        self._av_config: dict[str, Any] = {}
        if self._find_slot("system") is None:
            av = None
            try:
                av = self.store.get_active_version(self.agent_id)
            except Exception:
                av = None
            if av is None:
                # Last resort — try the latest version row even if no
                # active pointer is set. Mirrors store.get_agent_def.
                try:
                    av = self.store.latest_version(self.agent_id)
                except Exception:
                    av = None
            prompt = (av or {}).get("prompt_content") if isinstance(av, dict) else None
            if not prompt:
                raise ValueError(
                    f"agent {self.agent_id!r} has no prompt source: no "
                    "slot='system' binding and no agent_versions.prompt_content. "
                    "Populate one via the UI prompt editor or "
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

            # Load version files so schemas declared in agent.toml
            # ([composition].output_schema = "output_schema.json") can be
            # resolved from the active agent_version row when no explicit
            # output_schema binding exists. Production stores these via
            # POST /agents/{id}/versions/{v}/files.
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
        if self._find_slot("system") or self._av_prompt is not None:
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
        from agentbox.core.prompt.rendering import render_for_type

        rendered = render_for_type(b["type"], b.get("blobs") or [])
        return rendered.get("text") or ""

    def read_system(self) -> str:
        b = self._find_slot("system")
        if b is None:
            if self._av_prompt is not None:
                return self._av_prompt
            raise FileNotFoundError(
                f"agent {self.agent_id!r} has no slot='system' binding "
                "and no agent_versions.prompt_content fallback"
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

    def _av_schema_path(self, slot: str) -> str | None:
        """Return the schema path declared in the agent_version's
        composition snapshot (TOML-shaped), when the schema file is also
        present in ``agent_version_files``. Acts as the DB-side analogue
        of reading ``output_schema.json`` from the bundle on disk."""
        comp = self._av_config.get("composition") if isinstance(self._av_config, dict) else None
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
                    _INPUT_SCHEMA_PSEUDO if slot == "input_schema" else _OUTPUT_SCHEMA_PSEUDO
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
        elif self._av_prompt is not None:
            files[_SYS_PSEUDO] = self._av_prompt
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
