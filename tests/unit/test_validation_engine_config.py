"""Tests for output_validation_engine config on RunnerSpec."""

from __future__ import annotations

import pytest
from agentbox.core.data import RunnerSpec
from pydantic import ValidationError


class TestOutputValidationEngine:
    def test_default_is_both(self) -> None:
        spec = RunnerSpec()
        assert spec.output_validation_engine == "both"

    def test_accepts_jsonschema(self) -> None:
        spec = RunnerSpec(output_validation_engine="jsonschema")
        assert spec.output_validation_engine == "jsonschema"

    def test_accepts_pydantic(self) -> None:
        spec = RunnerSpec(output_validation_engine="pydantic")
        assert spec.output_validation_engine == "pydantic"

    def test_accepts_both(self) -> None:
        spec = RunnerSpec(output_validation_engine="both")
        assert spec.output_validation_engine == "both"

    def test_rejects_invalid_value(self) -> None:
        with pytest.raises(ValidationError):
            RunnerSpec(output_validation_engine="invalid")

    def test_roundtrips_with_other_fields(self) -> None:
        spec = RunnerSpec(
            timeout_seconds=300,
            output_schema_path="output_schema.json",
            output_validation_engine="pydantic",
            max_validation_retries=2,
        )
        assert spec.timeout_seconds == 300
        assert spec.output_schema_path == "output_schema.json"
        assert spec.output_validation_engine == "pydantic"
        assert spec.max_validation_retries == 2
