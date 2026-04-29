"""Tests for validation engine hint appended to system prompt."""

from __future__ import annotations

from agentbox.core.composition import _append_validation_engine_hint


class TestAppendValidationEngineHint:
    def test_both_engine_hint(self) -> None:
        result = _append_validation_engine_hint("## Role\n\nYou are a helper.", "both")
        assert "validated twice" in result
        assert "JSON Schema" in result
        assert "pydantic" in result

    def test_jsonschema_engine_hint(self) -> None:
        result = _append_validation_engine_hint("## Role\n\nYou are a helper.", "jsonschema")
        assert "JSON Schema" in result
        assert "validated twice" not in result

    def test_pydantic_engine_hint(self) -> None:
        result = _append_validation_engine_hint("## Role\n\nYou are a helper.", "pydantic")
        assert "pydantic" in result
        assert "validated twice" not in result

    def test_empty_text(self) -> None:
        result = _append_validation_engine_hint("", "both")
        assert "## Validation" in result

    def test_unknown_engine_defaults_to_both(self) -> None:
        result = _append_validation_engine_hint("## Role\n\nYou are a helper.", "unknown")
        assert "validated twice" in result
