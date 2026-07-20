"""Unit tests for PromptComposer + PromptComposition.

Verifies:
1. Segments are assembled in the correct order.
2. to_composed_view() and to_preview_result() produce identical
   ``rendered_prompt`` / ``system`` text (structural invariant).
3. The Q1 change is present: references are wrapped under "## References\\n\\n".
4. The Q2 change is present: no validators-hint block in preview.rendered_prompt.
5. The composer delegates to the same rendering primitives as compose_from_source.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from agentbox.core.agents.composition.bundle import (
    BundleSource,
    OutputSchemaInfo,
    ReferenceSpec,
)
from agentbox.core.agents.composition.composer import (
    BaseSegment,
    InputSchemaSegment,
    PromptComposer,
    PromptComposition,
    ReferenceSegment,
)
from agentbox.core.agents.composition.rendering import (
    append_input_schema,
    append_schema,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

BASE_PROMPT = "You are a helpful assistant.\n\nAnswer concisely."
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}
REF_HEADING = "Context Docs"
REF_CONTENT = "# Some context\n\nThis is reference content."
REF2_HEADING = "Extra Docs"
REF2_CONTENT = "# Extra\n\nAdditional content."


def _make_source(
    *,
    base: str = BASE_PROMPT,
    input_schema: dict[str, Any] | None = None,
    refs: list[tuple[str, str, str]] | None = None,  # (path, heading, content)
    output_schema: dict[str, Any] | None = None,
    user_template: str | None = None,
) -> BundleSource:
    """Build a minimal BundleSource mock."""
    source = MagicMock(spec=BundleSource)
    source.read_system.return_value = base
    source.read_user_template.return_value = user_template
    source.read_input_schema.return_value = (
        OutputSchemaInfo(schema=input_schema, relative_path="input_schema.json")
        if input_schema is not None
        else None
    )
    source.read_output_schema.return_value = (
        OutputSchemaInfo(schema=output_schema, relative_path="output_schema.json")
        if output_schema is not None
        else None
    )
    ref_specs = []
    if refs:
        for path, heading, content in refs:
            ref_specs.append(ReferenceSpec(path=path, heading=heading))
        # read_reference maps path → content
        content_map = {path: content for path, heading, content in refs}
        source.read_reference.side_effect = lambda r: content_map[r.path]
    source.references.return_value = ref_specs

    # Bundle files for SHA computation
    files: dict[str, str] = {"system": base}
    if user_template:
        files["user_template"] = user_template
    if refs:
        for path, _, content in refs:
            files[path] = content
    if output_schema is not None:
        files["output_schema.json"] = json.dumps(output_schema)
    if input_schema is not None:
        files["input_schema.json"] = json.dumps(input_schema)
    source.bundle_files.return_value = files

    return source


def _compose(source: BundleSource, variables: dict[str, str] | None = None) -> PromptComposition:
    return PromptComposer().compose(source, variables or {})


# ── Segment assembly tests ─────────────────────────────────────────────────────


class TestSegmentAssembly:
    """Verify segments are produced in the correct order."""

    def test_base_only_produces_one_segment(self) -> None:
        source = _make_source()
        comp = _compose(source)
        assert len(comp.segments) == 1
        assert isinstance(comp.segments[0], BaseSegment)
        assert comp.segments[0].text == BASE_PROMPT

    def test_with_input_schema_second_segment(self) -> None:
        source = _make_source(input_schema=INPUT_SCHEMA)
        comp = _compose(source)
        assert len(comp.segments) == 2
        assert isinstance(comp.segments[0], BaseSegment)
        assert isinstance(comp.segments[1], InputSchemaSegment)

    def test_reference_comes_after_input_schema(self) -> None:
        source = _make_source(
            input_schema=INPUT_SCHEMA,
            refs=[("path/ref.md", REF_HEADING, REF_CONTENT)],
        )
        comp = _compose(source)
        types = [type(s).__name__ for s in comp.segments]
        assert types == ["BaseSegment", "InputSchemaSegment", "ReferenceSegment"]

    def test_full_order_base_input_ref_output(self) -> None:
        source = _make_source(
            input_schema=INPUT_SCHEMA,
            refs=[("path/ref.md", REF_HEADING, REF_CONTENT)],
            output_schema=SCHEMA,
        )
        comp = _compose(source)
        types = [type(s).__name__ for s in comp.segments]
        assert types == [
            "BaseSegment",
            "InputSchemaSegment",
            "ReferenceSegment",
            "OutputSchemaSegment",
        ]

    def test_two_references_produce_two_segments(self) -> None:
        source = _make_source(
            refs=[
                ("path/ref1.md", REF_HEADING, REF_CONTENT),
                ("path/ref2.md", REF2_HEADING, REF2_CONTENT),
            ]
        )
        comp = _compose(source)
        ref_segs = [s for s in comp.segments if isinstance(s, ReferenceSegment)]
        assert len(ref_segs) == 2
        assert ref_segs[0].heading == REF_HEADING
        assert ref_segs[1].heading == REF2_HEADING


# ── Text assembly tests ────────────────────────────────────────────────────────


class TestTextAssembly:
    """Verify the assembled text matches the expected canonical format."""

    def test_base_only_text_is_base(self) -> None:
        source = _make_source()
        comp = _compose(source)
        assert comp.text == BASE_PROMPT

    def test_input_schema_appended_via_rendering_primitive(self) -> None:
        source = _make_source(input_schema=INPUT_SCHEMA)
        comp = _compose(source)
        expected = append_input_schema(BASE_PROMPT, INPUT_SCHEMA)
        assert comp.text == expected

    def test_output_schema_appended_via_rendering_primitive(self) -> None:
        source = _make_source(output_schema=SCHEMA)
        comp = _compose(source)
        expected = append_schema(BASE_PROMPT, SCHEMA)
        assert comp.text == expected

    def test_reference_wrapped_under_references_header(self) -> None:
        """Q1: references appear under '## References\\n\\n' header."""
        source = _make_source(refs=[("path/ref.md", REF_HEADING, REF_CONTENT)])
        comp = _compose(source)
        assert "## References\n\n" in comp.text
        assert f"## {REF_HEADING}\n\n{REF_CONTENT}" in comp.text

    def test_two_references_joined_under_one_header(self) -> None:
        source = _make_source(
            refs=[
                ("path/ref1.md", REF_HEADING, REF_CONTENT),
                ("path/ref2.md", REF2_HEADING, REF2_CONTENT),
            ]
        )
        comp = _compose(source)
        text = comp.text
        # Only ONE "## References" header
        assert text.count("## References\n\n") == 1
        # Both sections present
        assert f"## {REF_HEADING}" in text
        assert f"## {REF2_HEADING}" in text
        # REF_HEADING appears BEFORE REF2_HEADING
        assert text.index(f"## {REF_HEADING}") < text.index(f"## {REF2_HEADING}")

    def test_full_composition_order_matches_expected(self) -> None:
        source = _make_source(
            input_schema=INPUT_SCHEMA,
            refs=[("path/ref.md", REF_HEADING, REF_CONTENT)],
            output_schema=SCHEMA,
        )
        comp = _compose(source)
        text = comp.text

        # Build expected manually using same primitives
        expected = append_input_schema(BASE_PROMPT, INPUT_SCHEMA)
        expected = expected.rstrip() + "\n\n" + "## References\n\n" + f"## {REF_HEADING}\n\n{REF_CONTENT}"
        expected = append_schema(expected, SCHEMA)

        assert text == expected


# ── Q1: ## References header ───────────────────────────────────────────────────


class TestQ1ReferencesHeader:
    """Confirm the '## References' header is canonical in assembled text and preview."""

    def test_text_has_references_header(self) -> None:
        source = _make_source(refs=[("p/r.md", "My Ref", "content")])
        comp = _compose(source)
        assert "## References\n\n" in comp.text

    def test_to_preview_result_has_references_header(self) -> None:
        source = _make_source(refs=[("p/r.md", "My Ref", "content")])
        comp = _compose(source)
        result = comp.to_preview_result()
        assert "## References\n\n" in result["rendered_prompt"]

    def test_no_references_no_header(self) -> None:
        source = _make_source()
        comp = _compose(source)
        assert "## References" not in comp.text


# ── Structural invariant ───────────────────────────────────────────────────────


class TestStructuralInvariant:
    """to_preview_result().rendered_prompt == comp.text (the runtime text)."""

    def test_invariant_base_only(self) -> None:
        source = _make_source()
        comp = _compose(source)
        assert comp.to_preview_result()["rendered_prompt"] == comp.text

    def test_invariant_with_input_schema(self) -> None:
        source = _make_source(input_schema=INPUT_SCHEMA)
        comp = _compose(source)
        assert comp.to_preview_result()["rendered_prompt"] == comp.text

    def test_invariant_with_references(self) -> None:
        source = _make_source(refs=[("p/r.md", "My Ref", "content")])
        comp = _compose(source)
        assert comp.to_preview_result()["rendered_prompt"] == comp.text

    def test_invariant_with_output_schema(self) -> None:
        source = _make_source(output_schema=SCHEMA)
        comp = _compose(source)
        assert comp.to_preview_result()["rendered_prompt"] == comp.text

    def test_invariant_full_agent(self) -> None:
        """Full agent: base + input_schema + reference + output_schema."""
        source = _make_source(
            input_schema=INPUT_SCHEMA,
            refs=[("p/r.md", REF_HEADING, REF_CONTENT)],
            output_schema=SCHEMA,
        )
        comp = _compose(source)
        preview_text = comp.to_preview_result()["rendered_prompt"]
        assert preview_text == comp.text


# ── Q2: No validators-hint in preview ─────────────────────────────────────────


class TestQ2NoValidatorsHint:
    """Preview rendered_prompt does NOT include the validators-hint block."""

    def test_preview_no_validation_block(self) -> None:
        """_validation_block_for_preview is absent from composer output."""
        source = _make_source(output_schema=SCHEMA)
        comp = _compose(source)
        result = comp.to_preview_result()
        # The old preview appended a "## Validation" or "## Constraints" block.
        # After Q2, neither appears in the rendered_prompt.
        assert "## Validation" not in result["rendered_prompt"]
        assert "## Constraints" not in result["rendered_prompt"]

    def test_preview_validation_field_is_none(self) -> None:
        """validation metadata field is None when composer provides no validators."""
        source = _make_source(output_schema=SCHEMA)
        comp = _compose(source)
        result = comp.to_preview_result()
        assert result["validation"] is None


# ── Composition derived properties ────────────────────────────────────────────


class TestCompositionProperties:
    """Verify PromptComposition derived property accessors."""

    def test_base_is_raw_prompt(self) -> None:
        source = _make_source(input_schema=INPUT_SCHEMA, output_schema=SCHEMA)
        comp = _compose(source)
        assert comp.base == BASE_PROMPT

    def test_output_schema_property(self) -> None:
        source = _make_source(output_schema=SCHEMA)
        comp = _compose(source)
        assert comp.output_schema == SCHEMA

    def test_input_schema_property(self) -> None:
        source = _make_source(input_schema=INPUT_SCHEMA)
        comp = _compose(source)
        assert comp.input_schema == INPUT_SCHEMA

    def test_references_list_populated(self) -> None:
        source = _make_source(refs=[("p/r.md", REF_HEADING, REF_CONTENT)])
        comp = _compose(source)
        assert len(comp.references) == 1
        assert comp.references[0].heading == REF_HEADING
        assert comp.references[0].content == REF_CONTENT

    def test_bundle_sha_is_sha256_hex(self) -> None:
        source = _make_source()
        comp = _compose(source)
        assert isinstance(comp.bundle_sha, str)
        assert len(comp.bundle_sha) == 64  # SHA-256 hex

    def test_to_composed_reference(self) -> None:
        """ReferenceSegment.to_composed_reference() round-trips correctly."""
        source = _make_source(refs=[("p/r.md", REF_HEADING, REF_CONTENT)])
        comp = _compose(source)
        ref = comp.references[0].to_composed_reference()
        assert ref.path == "p/r.md"
        assert ref.heading == REF_HEADING
        assert ref.content == REF_CONTENT


# ── Delta check vs old compose_from_source ────────────────────────────────────


class TestDeltaVsOldRuntime:
    """Confirm the only change vs old compose_from_source is the Q1 header."""

    def test_agent_without_references_text_identical(self) -> None:
        """No reference → no change; composer text == old compose_from_source."""
        from agentbox.core.agents.composition.bundle import compose_from_source

        source = _make_source(input_schema=INPUT_SCHEMA, output_schema=SCHEMA)
        new_text = _compose(source).text
        old_result = compose_from_source(source, {})
        assert new_text == old_result.system

    def test_agent_with_references_adds_header_only(self) -> None:
        """With references: new text == old text with '## References\\n\\n' inserted."""
        from agentbox.core.agents.composition.bundle import compose_from_source

        source = _make_source(refs=[("p/r.md", REF_HEADING, REF_CONTENT)])
        new_text = _compose(source).text
        old_result = compose_from_source(source, {})

        # Old text: "...base\n\n## Context Docs\n\ncontent"
        # New text: "...base\n\n## References\n\n## Context Docs\n\ncontent"
        assert "## References\n\n" not in old_result.system
        assert "## References\n\n" in new_text

        # The delta is EXACTLY "## References\n\n" inserted before the first "## "
        # reference section.
        old_ref_pos = old_result.system.index(f"## {REF_HEADING}")
        new_ref_pos = new_text.index(f"## {REF_HEADING}")
        header = "## References\n\n"
        assert new_ref_pos == old_ref_pos + len(header)
        # Text before the ref section is the same (accounting for header offset)
        assert old_result.system[:old_ref_pos] == new_text[:old_ref_pos]
        # Text from the ref section onward is the same
        assert old_result.system[old_ref_pos:] == new_text[new_ref_pos:]
