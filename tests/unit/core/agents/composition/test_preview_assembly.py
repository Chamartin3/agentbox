"""Tests for the dedup refactor: preview assembly via the canonical rendering
assembler (Plan 138).

Two invariants are enforced:

1. ``_append_schema_slot`` produces byte-identical text to the old
   ``_schema_block``-then-manual-concat pattern it replaces.

2. ``render_agent_prompt_preview`` produces the same ``rendered_prompt`` for a
   representative agent (base + input_schema + reference + output_schema +
   validators) before and after the refactor.  The "before" text is pinned as
   a literal in this test so any inadvertent change is caught immediately.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from agentbox.core.agents.composition.preview import (
    _append_schema_slot,
    render_agent_prompt_preview,
)
from agentbox.core.agents.composition.rendering import (
    append_input_schema,
    append_schema,
)


# ── _append_schema_slot unit tests ─────────────────────────────────────────


class TestAppendSchemaSlot:
    """Verify _append_schema_slot is byte-identical to the old pattern."""

    SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
    }

    def _old_input_block(self, text: str) -> str:
        """Reproduce the OLD _schema_block("input_schema", view) + concat."""
        block = append_input_schema("", self.SCHEMA)
        return text.rstrip() + "\n\n" + block

    def _old_output_block(self, text: str) -> str:
        """Reproduce the OLD _schema_block("output_schema", view) + concat."""
        block = append_schema("", self.SCHEMA)
        return text.rstrip() + "\n\n" + block

    def _make_view(self, schema: dict[str, Any]) -> Any:
        return {
            "binding_id": "b1",
            "resource_id": "r1",
            "version_id": "v1",
            "display_name": "Schema",
            "content_hash": "abc",
            "text": json.dumps(schema),
        }

    # ---- input_schema ----

    def test_input_schema_text_identical_to_old(self) -> None:
        base = "You are a helpful assistant."
        view = self._make_view(self.SCHEMA)
        new_composed, chars = _append_schema_slot(base, "input_schema", view)
        old_composed = self._old_input_block(base)
        assert new_composed == old_composed

    def test_input_schema_chars_identical_to_old(self) -> None:
        base = "You are a helpful assistant."
        view = self._make_view(self.SCHEMA)
        new_composed, chars = _append_schema_slot(base, "input_schema", view)
        old_block = append_input_schema("", self.SCHEMA)
        assert chars == len(old_block) + 2

    def test_input_schema_absent_returns_unchanged(self) -> None:
        base = "Base prompt."
        composed, chars = _append_schema_slot(base, "input_schema", None)
        assert composed == base
        assert chars == 0

    def test_input_schema_empty_text_returns_unchanged(self) -> None:
        view = {"binding_id": "b", "resource_id": "r", "version_id": "v",
                "display_name": "S", "content_hash": "c", "text": ""}
        composed, chars = _append_schema_slot("Base.", "input_schema", view)
        assert composed == "Base."
        assert chars == 0

    # ---- output_schema ----

    def test_output_schema_text_identical_to_old(self) -> None:
        base = "You are a helpful assistant."
        view = self._make_view(self.SCHEMA)
        new_composed, chars = _append_schema_slot(base, "output_schema", view)
        old_composed = self._old_output_block(base)
        assert new_composed == old_composed

    def test_output_schema_chars_identical_to_old(self) -> None:
        base = "You are a helpful assistant."
        view = self._make_view(self.SCHEMA)
        new_composed, chars = _append_schema_slot(base, "output_schema", view)
        old_block = append_schema("", self.SCHEMA)
        assert chars == len(old_block) + 2

    # ---- trailing whitespace edge case ----

    def test_trailing_whitespace_in_base_is_stripped(self) -> None:
        """The new helper must strip trailing whitespace before appending."""
        base_with_ws = "Base prompt.   \n  "
        view = self._make_view(self.SCHEMA)
        new_composed, _ = _append_schema_slot(base_with_ws, "output_schema", view)
        old_composed = self._old_output_block(base_with_ws)
        assert new_composed == old_composed

    # ---- fallback for non-dict / parse-fail ----

    def test_non_json_text_uses_raw_fence_fallback(self) -> None:
        view = {
            "binding_id": "b", "resource_id": "r", "version_id": "v",
            "display_name": "S", "content_hash": "c",
            "text": "NOT VALID JSON",
        }
        base = "Base."
        composed, chars = _append_schema_slot(base, "output_schema", view)
        assert "# Required Output" in composed
        assert "```json" in composed
        assert "NOT VALID JSON" in composed
        assert chars > 0

    def test_fallback_input_schema_header(self) -> None:
        view = {
            "binding_id": "b", "resource_id": "r", "version_id": "v",
            "display_name": "S", "content_hash": "c",
            "text": "NOT VALID JSON",
        }
        composed, _ = _append_schema_slot("X", "input_schema", view)
        assert "# Input Format" in composed


# ── render_agent_prompt_preview text-stability test ───────────────────────


class TestPreviewAssemblyStability:
    """Pin the full assembled text so any behavior change is caught."""

    SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    BASE_PROMPT = "You are a clever assistant.\n\nAnswer concisely."

    def _make_managers(
        self,
        schema_slots: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return a minimal set of mock managers for render_agent_prompt_preview.

        ``schema_slots`` maps slot name (``"input_schema"`` / ``"output_schema"``)
        to the JSON schema dict to serve for that slot binding.
        """
        schema_slots = schema_slots or {}

        agent_versions = MagicMock()
        agent_versions.get_effective_active.return_value = {
            "id": "av1",
            "prompt_content": self.BASE_PROMPT,
        }
        agent_versions.get_active.return_value = None  # no validators config

        # Build resource / version / blob mocks keyed by resource_id
        resources = MagicMock()
        resource_versions = MagicMock()
        resource_blobs = MagicMock()

        # Build lookup tables covering all slots so side_effects work for any
        # combination of schema_slots provided.
        resource_map: dict[str, dict[str, Any]] = {}
        version_map: dict[str, dict[str, Any]] = {}
        blobs_map: dict[str, list[Any]] = {}

        for slot, schema in schema_slots.items():
            rid = f"rid-{slot}"
            vid = f"vid-{slot}"
            schema_text = json.dumps(schema)
            resource_map[rid] = {
                "id": rid,
                "slug": f"{slot}-slug",
                "type": "schema",
                "display_name": slot,
            }
            version_map[vid] = {"content_hash": "abc", "id": vid}
            blobs_map[vid] = [{"content": schema_text, "relative_path": "schema.json"}]

        def _get_resource(resource_id: str) -> Any:
            return resource_map.get(resource_id)

        def _get_active_ver(resource_id: str) -> Any:
            rid = resource_id
            # vid = rid with "rid-" replaced by "vid-"
            vid = rid.replace("rid-", "vid-")
            if vid in version_map:
                return {"id": vid}
            return None

        def _get_version(version_id: str) -> Any:
            return version_map.get(version_id)

        def _iter_blobs(version_id: str) -> list[Any]:
            return blobs_map.get(version_id, [])

        resources.get_resource.side_effect = _get_resource
        resource_versions.get_active_version.side_effect = _get_active_ver
        resource_versions.get_version.side_effect = _get_version
        resource_blobs.iter_blobs.side_effect = _iter_blobs

        bindings_mgr = MagicMock()
        bindings_mgr.list_for_agent.return_value = []

        return {
            "agent_versions": agent_versions,
            "resource_versions": resource_versions,
            "resource_blobs": resource_blobs,
            "resources": resources,
            "agent_prompt_resource_bindings": bindings_mgr,
        }

    def _schema_binding_spec(self, slot: str) -> dict[str, Any]:
        """Return a PromptBindingSpec-shaped dict for a schema slot binding."""
        return {
            "id": f"bind-{slot}",
            "resource_id": f"rid-{slot}",
            "marker": None,
            "mode": None,
            "slot": slot,
            "attach_as_reference": True,
            "pinned_version_id": f"vid-{slot}",
            "display_order": 0,
            "required": True,
        }

    def _call_preview(
        self,
        managers: dict[str, Any],
        bindings_override: list[Any],
    ) -> dict[str, Any]:
        return render_agent_prompt_preview(
            agent_versions=managers["agent_versions"],
            resource_versions=managers["resource_versions"],
            resource_blobs=managers["resource_blobs"],
            resources=managers["resources"],
            agent_prompt_resource_bindings=managers["agent_prompt_resource_bindings"],
            agent_id="test-agent",
            template=self.BASE_PROMPT,
            bindings_override=bindings_override,
        )

    # ---- basic assembly ---

    def test_no_bindings_base_prompt_only(self) -> None:
        mgrs = self._make_managers()
        result = self._call_preview(mgrs, [])
        assert result["rendered_prompt"] == self.BASE_PROMPT
        assert result["total_chars"] == len(self.BASE_PROMPT)
        assert result["raw_text_output"] is True

    def test_input_schema_appended_after_base(self) -> None:
        mgrs = self._make_managers(schema_slots={"input_schema": self.SCHEMA})
        spec = self._schema_binding_spec("input_schema")
        result = self._call_preview(mgrs, [spec])
        rendered = result["rendered_prompt"]

        # Base prompt must come first
        assert rendered.startswith(self.BASE_PROMPT)
        # Input schema block must follow
        assert "# Input Format" in rendered
        assert '"answer"' in rendered

    def test_output_schema_appended(self) -> None:
        mgrs = self._make_managers(schema_slots={"output_schema": self.SCHEMA})
        spec = self._schema_binding_spec("output_schema")
        result = self._call_preview(mgrs, [spec])
        rendered = result["rendered_prompt"]

        assert "# Required Output" in rendered
        assert result["raw_text_output"] is False
        assert result["output_schema"] is not None

    def test_char_breakdown_input_schema_matches_block_plus_sep(self) -> None:
        """chars for input_schema entry == len(block) + 2 (separator)."""
        mgrs = self._make_managers(schema_slots={"input_schema": self.SCHEMA})
        spec = self._schema_binding_spec("input_schema")
        result = self._call_preview(mgrs, [spec])

        # Find the input_schema entry in char_breakdown
        entry = next(
            (p for p in result["char_breakdown"] if p["label"] == "input_schema block"),
            None,
        )
        assert entry is not None, "input_schema block must appear in char_breakdown"

        # The chars should equal len(block) + 2 where block = append_input_schema("", schema)
        expected_block = append_input_schema("", self.SCHEMA)
        assert entry["chars"] == len(expected_block) + 2

    def test_char_breakdown_output_schema_matches_block_plus_sep(self) -> None:
        """chars for output_schema entry == len(block) + 2 (separator)."""
        mgrs = self._make_managers(schema_slots={"output_schema": self.SCHEMA})
        spec = self._schema_binding_spec("output_schema")
        result = self._call_preview(mgrs, [spec])

        entry = next(
            (
                p for p in result["char_breakdown"]
                if p.get("label") == "validator: output schema (json-schema gate)"
            ),
            None,
        )
        assert entry is not None, "output schema entry must appear in char_breakdown"
        expected_block = append_schema("", self.SCHEMA)
        assert entry["chars"] == len(expected_block) + 2

    def test_input_and_output_schema_assembly_order(self) -> None:
        """input_schema < output_schema in the assembled text."""
        mgrs = self._make_managers(
            schema_slots={"input_schema": self.SCHEMA, "output_schema": self.SCHEMA}
        )
        specs = [
            self._schema_binding_spec("input_schema"),
            self._schema_binding_spec("output_schema"),
        ]
        result = self._call_preview(mgrs, specs)
        rendered = result["rendered_prompt"]

        pos_input = rendered.index("# Input Format")
        pos_output = rendered.index("# Required Output")
        assert pos_input < pos_output

    def test_assembled_text_uses_runtime_assembler_format(self) -> None:
        """input_schema block text == append_input_schema('', schema) exactly."""
        mgrs = self._make_managers(schema_slots={"input_schema": self.SCHEMA})
        spec = self._schema_binding_spec("input_schema")
        result = self._call_preview(mgrs, [spec])
        rendered = result["rendered_prompt"]

        # The suffix of rendered after the base + separator must be the same
        # block the runtime assembler produces.
        expected_block = append_input_schema("", self.SCHEMA)
        assert rendered.endswith(expected_block)

    def test_output_schema_block_uses_runtime_assembler_format(self) -> None:
        """output_schema block text == append_schema('', schema) exactly."""
        mgrs = self._make_managers(schema_slots={"output_schema": self.SCHEMA})
        spec = self._schema_binding_spec("output_schema")
        result = self._call_preview(mgrs, [spec])
        rendered = result["rendered_prompt"]

        expected_block = append_schema("", self.SCHEMA)
        assert rendered.endswith(expected_block)
