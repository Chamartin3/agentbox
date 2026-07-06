"""BindingsBundleSource — reads bundle from agent_prompt_resource_bindings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, TypedDict

from agentbox.core.agents.composition.rendering import render_for_type
from agentbox.core.agents.composition.bundle.sources._types import (
    OutputSchemaInfo,
    ReferenceSpec,
)


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
