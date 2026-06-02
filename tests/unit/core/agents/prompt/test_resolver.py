"""Tests for `{{resource:marker}}` prompt resolution."""

from __future__ import annotations

import pytest

from agentbox.core.agents.prompt.resolver import (
    PromptResolution,
    ResolvedBinding,
    resolve_prompt,
)


def _binding(
    binding_id: str = "b1",
    marker: str = "res1",
    type: str = "document",
    mode: str = "inline",
    content: str = "rendered content",
) -> dict:
    return {
        "binding_id": binding_id,
        "marker": marker,
        "resource_id": "r1",
        "version_id": "v1",
        "content_hash": "abc",
        "type": type,
        "mode": mode,
        "blobs": [{"content": content}],
        "display_name": "Test Resource",
        "required": True,
    }


class TestResolvePrompt:
    def test_replaces_single_marker(self) -> None:
        result = resolve_prompt(
            "Before {{resource:res1}} After",
            [_binding(marker="res1")],
        )
        assert result.rendered_prompt == "Before rendered content After"
        assert len(result.snapshot) == 1
        assert result.unresolved_markers == []
        assert result.warnings == []

    def test_replaces_multiple_markers(self) -> None:
        result = resolve_prompt(
            "A {{resource:a}} and {{resource:b}}",
            [
                _binding(binding_id="1", marker="a", content="alpha"),
                _binding(binding_id="2", marker="b", content="beta"),
            ],
        )
        assert result.rendered_prompt == "A alpha and beta"

    def test_multiple_bindings_same_marker_join(self) -> None:
        result = resolve_prompt(
            "{{resource:dup}}",
            [
                _binding(binding_id="1", marker="dup", content="first"),
                _binding(binding_id="2", marker="dup", content="second"),
            ],
        )
        assert "first\n\nsecond" in result.rendered_prompt

    def test_unresolved_marker_becomes_empty(self) -> None:
        result = resolve_prompt(
            "{{resource:missing}}",
            [],
        )
        assert result.rendered_prompt == ""
        assert "missing" in result.unresolved_markers

    def test_unused_required_binding_warns(self) -> None:
        result = resolve_prompt(
            "no markers here",
            [_binding(marker="unused")],
        )
        assert len(result.warnings) == 1
        assert "unused" in result.warnings[0]

    def test_non_required_binding_skips_value_error(self) -> None:
        binding = _binding(marker="bad", type="folder", mode="invalid_mode")
        binding["required"] = False
        result = resolve_prompt("{{resource:bad}}", [binding])
        assert result.rendered_prompt == ""
        assert len(result.warnings) == 1

    def test_required_binding_raises_on_value_error(self) -> None:
        binding = _binding(marker="bad", type="folder", mode="invalid_mode")
        binding["required"] = True
        with pytest.raises(ValueError):
            resolve_prompt("{{resource:bad}}", [binding])

    def test_skips_markerless_bindings(self) -> None:
        binding = _binding(marker="res1")
        binding.pop("marker")
        binding["mode"] = ""  # also no mode
        result = resolve_prompt("text", [binding])
        assert result.snapshot == []

    def test_name_only_mode(self) -> None:
        result = resolve_prompt(
            "{{resource:res1}}",
            [_binding(marker="res1", mode="name_only")],
        )
        assert result.rendered_prompt == "- Test Resource"

    def test_resolved_binding_dataclass(self) -> None:
        rb = ResolvedBinding(
            binding_id="b1",
            marker="m",
            resource_id="r1",
            version_id="v1",
            content_hash="hash",
            type="document",
            mode="inline",
            rendered="text",
            required=True,
        )
        assert rb.binding_id == "b1"
        assert rb.rendered == "text"

    def test_prompt_resolution_dataclass(self) -> None:
        pr = PromptResolution(
            rendered_prompt="result",
            snapshot=[],
            unresolved_markers=[],
            warnings=[],
        )
        assert pr.rendered_prompt == "result"
