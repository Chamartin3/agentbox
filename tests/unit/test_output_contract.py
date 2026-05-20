"""Phase 2 — single-source-of-truth renderer for the output-contract block."""

from __future__ import annotations

from agentbox.core.agent.config import HttpValidatorConfig, OutputConfig
from agentbox.core.prompt.output_contract import append, render


def test_render_empty_returns_empty_string() -> None:
    assert render(OutputConfig()) == ""


def test_render_schema_only() -> None:
    out = render(OutputConfig(json_schema={"type": "object"}))
    assert "# Required Output" in out
    assert "```json" in out
    assert "## Constraints" not in out
    assert "## Validation" not in out


def test_render_legacy_rules_fallback() -> None:
    # Backwards-compat: when no validator carries a description,
    # contract-level rules[] still render as bullets.
    out = render(OutputConfig(rules=["Rule A.", "Rule B."]))
    assert "## Constraints" in out
    assert "- Rule A." in out
    assert "- Rule B." in out
    assert "# Required Output" not in out


def test_render_validator_descriptions() -> None:
    # Plan 22: validators own their constraint text via `description`.
    cfg = OutputConfig(
        validators=(
            HttpValidatorConfig(endpoint="http://x/api", description="Sum must be > 100."),
            HttpValidatorConfig(endpoint="http://y/api", description="No nulls."),
        ),
    )
    out = render(cfg)
    assert "## Constraints" in out
    assert "- Sum must be > 100." in out
    assert "- No nulls." in out


def test_render_validator_descriptions_win_over_legacy_rules() -> None:
    cfg = OutputConfig(
        rules=["legacy rule"],
        validators=(HttpValidatorConfig(endpoint="http://x/api", description="new rule"),),
    )
    out = render(cfg)
    assert "- new rule" in out
    assert "legacy rule" not in out


def test_render_full_block_byte_stable() -> None:
    cfg = OutputConfig(
        json_schema={"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}},
        validators=(
            HttpValidatorConfig(endpoint="http://x/api", description="Sum must be > 100."),
            HttpValidatorConfig(endpoint="http://y/api", description="No nulls allowed."),
        ),
    )
    a = render(cfg)
    b = render(cfg)
    assert a == b
    assert a.index("# Required Output") < a.index("## Constraints")
    assert "## Validation" not in a


def test_append_preserves_base_and_separates_with_blank_line() -> None:
    cfg = OutputConfig(
        validators=(HttpValidatorConfig(endpoint="http://x/api", description="one."),),
    )
    out = append("base prompt", cfg)
    assert out.startswith("base prompt\n\n## Constraints")


def test_append_noop_when_config_empty() -> None:
    assert append("base", OutputConfig()) == "base"
