"""PromptComposer — single owner of agent system-prompt assembly.

Every consumer (runtime, preview, snapshot) is a thin projection over the
composed segments; the assembly order and per-section rendering rules exist
in exactly ONE place.

Design
------
Segments are produced in a canonical order:

  BaseSegment → InputSchemaSegment → ReferenceSegment(s) → OutputSchemaSegment

The assembled ``PromptComposition.text`` is the canonical prompt the model
sees.  Both projections derive their ``rendered_prompt`` / ``system`` from the
same ``text``, enforcing the structural invariant:

    to_preview_result().rendered_prompt == text == what the runtime uses

Delegation
----------
Segment rendering delegates to the existing ``composition/rendering.append*``
primitives so formatting stays the single source of truth.

Boundaries
----------
- This module lives in ``core/agents/composition/`` (render logic — domain,
  not data).
- ``build_prompt`` in ``build.py`` calls the composer and then independently
  applies ``append_validation_engine_hint`` on the resulting text;
  that post-composer step is NOT part of the segments and does not affect the
  structural invariant.
- ``to_preview_result()`` takes an optional ``refs_meta`` override so the
  preview service can provide binding-aware metadata (binding_id, version_id)
  that the composer cannot know (it only has segment data).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from agentbox.core.agents.composition.bundle import (
    BundleSource,
    _format_template,
    _ref_heading_fallback,
)
from agentbox.core.agents.composition.rendering import (
    append_input_schema,
    append_schema,
)
from agentbox.core.data.composition import ComposedReference
from agentbox.core.data.payload_types import (
    CharBreakdownPart,
    JsonSchemaDict,
    PromptPreviewResult,
    ReferenceMetaView,
    SnapshotEntryView,
)

logger = logging.getLogger(__name__)


# ── Segments ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BaseSegment:
    """The base system prompt (from ``agent_versions.prompt_content``)."""

    text: str
    label: str = "prompt template"

    def render(self) -> str:
        return self.text


@dataclass(frozen=True)
class InputSchemaSegment:
    """Input-format instruction block derived from the input_schema binding."""

    schema: JsonSchemaDict
    label: str = "input_schema block"

    def render(self, base: str) -> str:
        """Return the base with the input-schema block appended."""
        return append_input_schema(base, self.schema)


@dataclass(frozen=True)
class ReferenceSegment:
    """One reference section.

    ``path`` and ``heading`` identify the reference; ``content`` is the
    rendered blob text.  The ``## References`` group header is emitted by
    ``_assemble()`` when the first reference is encountered.
    """

    path: str
    heading: str
    content: str

    @property
    def label(self) -> str:
        return self.heading

    def render_section(self) -> str:
        """Render as a ``## {heading}`` section."""
        return f"## {self.heading}\n\n{self.content}"

    def to_composed_reference(self) -> ComposedReference:
        return ComposedReference(
            path=self.path, heading=self.heading, content=self.content
        )


@dataclass(frozen=True)
class OutputSchemaSegment:
    """Structured-output instruction block derived from the output_schema binding."""

    schema: JsonSchemaDict
    schema_sha: str
    label: str = "output_schema block"

    def render(self, base: str) -> str:
        """Return the base with the output-schema block appended."""
        return append_schema(base, self.schema)


Segment = BaseSegment | InputSchemaSegment | ReferenceSegment | OutputSchemaSegment


# ── Diagnostics ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CompositionDiagnostics:
    unresolved_markers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── PromptComposition ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PromptComposition:
    """Canonical composition result — all consumers derive from this.

    ``segments`` is the ordered list of typed segments; all other properties
    are derived from them so there is only one assembly code path.

    Structural invariant:
        ``to_preview_result()["rendered_prompt"] == self.text``

    This holds by construction: both sides call ``_assemble(segments)`` and
    the preview path never appends extra blocks to the rendered text.
    """

    segments: tuple[Segment, ...]
    diagnostics: CompositionDiagnostics
    bundle_sha: str
    user: str = ""
    # Raw user template text (before variables substitution), for preview.
    user_template: str | None = None

    # ── derived properties ──────────────────────────────────────────────

    @property
    def base(self) -> str:
        for s in self.segments:
            if isinstance(s, BaseSegment):
                return s.text
        return ""

    @property
    def references(self) -> list[ReferenceSegment]:
        return [s for s in self.segments if isinstance(s, ReferenceSegment)]

    @property
    def input_schema(self) -> JsonSchemaDict | None:
        for s in self.segments:
            if isinstance(s, InputSchemaSegment):
                return s.schema
        return None

    @property
    def output_schema(self) -> JsonSchemaDict | None:
        for s in self.segments:
            if isinstance(s, OutputSchemaSegment):
                return s.schema
        return None

    @property
    def output_schema_sha(self) -> str | None:
        for s in self.segments:
            if isinstance(s, OutputSchemaSegment):
                return s.schema_sha
        return None

    @property
    def text(self) -> str:
        """The canonical assembled prompt text.

        Runtime and preview both derive their rendered text from this property.
        """
        return _assemble(self.segments)

    @property
    def total_chars(self) -> int:
        return len(self.text)

    # ── projections ────────────────────────────────────────────────────

    def to_preview_result(
        self,
        *,
        snapshot: list[SnapshotEntryView] | None = None,
        unresolved_markers: list[str] | None = None,
        warnings: list[str] | None = None,
        refs_meta: list[ReferenceMetaView] | None = None,
    ) -> PromptPreviewResult:
        """Preview projection: same ``rendered_prompt`` as runtime + UI metadata.

        ``rendered_prompt`` equals ``self.text`` by construction — the structural
        invariant.  The validators-hint block that the old ``preview.py`` helper
        appended is intentionally absent (Q2 decision).

        Args:
            snapshot: Binding resolution snapshot entries (from resolve_prompt).
            unresolved_markers: Markers not found in the prompt template.
            warnings: Resolver warnings.
            refs_meta: Binding-aware reference metadata from the preview service.
                When absent, minimal metadata (path + heading only) is generated
                from the reference segments.
        """
        rendered = self.text
        ref_segs = self.references

        # ── Char breakdown ─────────────────────────────────────────────
        breakdown: list[CharBreakdownPart] = []
        for s in self.segments:
            if isinstance(s, BaseSegment):
                breakdown.append({"label": "prompt template", "chars": len(s.render())})
            elif isinstance(s, InputSchemaSegment):
                block = append_input_schema("", s.schema)
                breakdown.append({"label": "input_schema block", "chars": len(block) + 2})
            elif isinstance(s, ReferenceSegment):
                section = s.render_section()
                chars = len(section) + 2
                # First reference absorbs the "## References\n\n" header cost.
                if ref_segs and s is ref_segs[0]:
                    chars += len("## References\n\n")
                breakdown.append({"label": s.heading, "chars": chars})
            elif isinstance(s, OutputSchemaSegment):
                block = append_schema("", s.schema)
                breakdown.append(
                    {
                        "label": "validator: output schema (json-schema gate)",
                        "kind": "validator",
                        "chars": len(block) + 2,
                    }
                )

        # ── Reference metadata ─────────────────────────────────────────
        if refs_meta is not None:
            raw_refs: list[ReferenceMetaView] = refs_meta
        else:
            raw_refs = [
                {
                    "binding_id": "",
                    "resource_id": s.path,
                    "version_id": "",
                    "display_name": s.heading,
                }
                for s in ref_segs
            ]

        return {
            "rendered_prompt": rendered,
            "base_prompt": self.base,
            "template": self.base,
            "unresolved_markers": (
                unresolved_markers
                if unresolved_markers is not None
                else self.diagnostics.unresolved_markers
            ),
            "warnings": (
                warnings if warnings is not None else self.diagnostics.warnings
            ),
            "references": raw_refs,
            "input_schema": None,
            "output_schema": None,
            "validation": None,
            "raw_text_output": self.output_schema is None,
            "char_breakdown": breakdown,
            "total_chars": len(rendered),
            "snapshot": snapshot if snapshot is not None else [],
        }


def _assemble(segments: tuple[Segment, ...]) -> str:
    """Build the canonical prompt text from ordered segments.

    References are grouped under a single ``## References`` header (Q1).
    All other blocks are appended in order using the rendering primitives.
    """
    text = ""
    refs: list[ReferenceSegment] = [s for s in segments if isinstance(s, ReferenceSegment)]

    for s in segments:
        if isinstance(s, BaseSegment):
            text = s.render()
        elif isinstance(s, InputSchemaSegment):
            text = s.render(text)
        elif isinstance(s, ReferenceSegment):
            # Emit the entire reference group when we hit the FIRST reference.
            if refs and s is refs[0]:
                ref_sections = "\n\n".join(r.render_section() for r in refs)
                refs_block = "## References\n\n" + ref_sections
                text = (text or "").rstrip() + "\n\n" + refs_block
        elif isinstance(s, OutputSchemaSegment):
            text = s.render(text)

    return text


# ── PromptComposer ────────────────────────────────────────────────────────────


class PromptComposer:
    """Builds a ``PromptComposition`` from any ``BundleSource``.

    Single entry point for all prompt assembly — runtime, preview, and
    snapshot are projections of the returned ``PromptComposition``.

    Usage::

        composition = PromptComposer().compose(source, variables=variables)
        system = composition.text             # runtime text
        preview = composition.to_preview_result(...)  # preview

    ``variables`` may be empty (``{}``) for previews where no run-time values
    are available; the base prompt is returned verbatim in that case.  Pass
    ``render=False`` to suppress all template substitution (raw braces kept
    verbatim — same semantics as ``compose_from_source(render=False)``).
    """

    def compose(
        self,
        source: BundleSource,
        variables: dict[str, str],
        *,
        render: bool = True,
    ) -> PromptComposition:
        """Compose all segments from *source* into a ``PromptComposition``."""
        # ── Base segment ───────────────────────────────────────────────
        system_raw = source.read_system()
        base_text = _format_template(system_raw, variables) if render else system_raw

        segments: list[Segment] = [BaseSegment(text=base_text)]

        # ── Input schema ───────────────────────────────────────────────
        input_schema_info = source.read_input_schema()
        if input_schema_info is not None:
            segments.append(InputSchemaSegment(schema=input_schema_info.schema))

        # ── References ─────────────────────────────────────────────────
        for ref in source.references():
            content = source.read_reference(ref)
            heading = ref.heading or _ref_heading_fallback(ref.path)
            segments.append(
                ReferenceSegment(path=ref.path, heading=heading, content=content)
            )

        # ── Output schema ──────────────────────────────────────────────
        schema_info = source.read_output_schema()
        if schema_info is not None:
            schema_sha = hashlib.sha256(
                json.dumps(
                    schema_info.schema, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            segments.append(
                OutputSchemaSegment(schema=schema_info.schema, schema_sha=schema_sha)
            )

        # ── Bundle SHA ─────────────────────────────────────────────────
        files_to_hash = source.bundle_files()
        canonical = "\n".join(
            f"{path}:{content}" for path, content in sorted(files_to_hash.items())
        )
        bundle_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        # ── User prompt ────────────────────────────────────────────────
        user_template = source.read_user_template()
        if user_template is not None:
            user = (
                _format_template(user_template, variables) if render else user_template
            )
        else:
            user = variables.get("user_message", "") if render else ""

        return PromptComposition(
            segments=tuple(segments),
            diagnostics=CompositionDiagnostics(),
            bundle_sha=bundle_sha,
            user=user,
            user_template=user_template,
        )


__all__ = [
    "BaseSegment",
    "CompositionDiagnostics",
    "InputSchemaSegment",
    "OutputSchemaSegment",
    "PromptComposer",
    "PromptComposition",
    "ReferenceSegment",
    "Segment",
]
