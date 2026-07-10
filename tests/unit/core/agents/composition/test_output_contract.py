"""Plan 22 — single-source-of-truth renderer for the output-contract block."""

from __future__ import annotations

from agentbox.core.agents import HttpValidatorConfig
from agentbox.core.agents.contract import OutputConfig, append, render


def test_render_empty_returns_empty_string() -> None:
    assert render(OutputConfig()) == ""


def test_render_schema_only() -> None:
    out = render(OutputConfig(json_schema={"type": "object"}))
    assert "# Required Output" in out
    assert "```json" in out
    assert "## Constraints" not in out
    assert "## Validation" not in out


def test_render_validator_descriptions() -> None:
    cfg = OutputConfig(
        validators=(
            HttpValidatorConfig(
                endpoint="http://x/api", description="Sum must be > 100."
            ),
            HttpValidatorConfig(endpoint="http://y/api", description="No nulls."),
        ),
    )
    out = render(cfg)
    assert "## Constraints" in out
    assert "- Sum must be > 100." in out
    assert "- No nulls." in out


def test_render_multiline_description_splits_into_bullets() -> None:
    cfg = OutputConfig(
        validators=(
            HttpValidatorConfig(
                endpoint="http://x/api",
                description="First constraint.\nSecond constraint.\nThird.",
            ),
        ),
    )
    out = render(cfg)
    assert "- First constraint." in out
    assert "- Second constraint." in out
    assert "- Third." in out


def test_render_skips_validators_without_description() -> None:
    cfg = OutputConfig(
        validators=(
            HttpValidatorConfig(endpoint="http://x/api"),
            HttpValidatorConfig(endpoint="http://y/api", description="present."),
        ),
    )
    out = render(cfg)
    assert "- present." in out


def test_render_full_block_byte_stable() -> None:
    cfg = OutputConfig(
        json_schema={
            "type": "object",
            "required": ["x"],
            "properties": {"x": {"type": "integer"}},
        },
        validators=(
            HttpValidatorConfig(
                endpoint="http://x/api", description="Sum must be > 100."
            ),
            HttpValidatorConfig(
                endpoint="http://y/api", description="No nulls allowed."
            ),
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
