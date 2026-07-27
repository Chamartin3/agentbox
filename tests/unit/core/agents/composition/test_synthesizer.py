"""Tests for the inline-to-composition synthesizer.

Verifies:
1. ``inline_to_composition`` adds a default ``CompositionConfig`` when
   ``agent.composition is None``.
2. It is a no-op when ``agent.composition`` is already set.
3. Byte-identity: for a plain inline-prompt agent, composing via a mock
   ``BindingsBundleSource`` that returns ``agent.prompt`` as the system text
   produces exactly the same text as the original ``agent.prompt``.
4. Byte-identity with prompt bindings: when prompt bindings exist (no
   slot-based schema bindings), the composed text equals ``agent.prompt``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agentbox.core.agents.composition.bundle import (
    BundleSource,
    OutputSchemaInfo,
)
from agentbox.core.agents.composition.composer import PromptComposer
from agentbox.core.agents.composition.synthesizer import inline_to_composition
from agentbox.core.data.agent_defs import AgentDef, CompositionConfig


# ── Helpers ────────────────────────────────────────────────────────────────────


def _inline_agent(prompt: str) -> AgentDef:
    """Build an inline-only agent (composition=None)."""
    return AgentDef(id="test-agent", prompt=prompt, composition=None)


def _agent_with_composition(prompt: str) -> AgentDef:
    """Build an agent that already has a composition block."""
    return AgentDef(id="test-agent", prompt=prompt, composition=CompositionConfig())


def _make_source(prompt: str) -> BundleSource:
    """Minimal BundleSource mock returning ``prompt`` as the system text."""
    source = MagicMock(spec=BundleSource)
    source.read_system.return_value = prompt
    source.read_user_template.return_value = None
    source.read_input_schema.return_value = None
    source.read_output_schema.return_value = None
    source.references.return_value = []
    source.bundle_files.return_value = {"system": prompt}
    return source


def _make_source_with_output_schema(
    prompt: str, schema: dict
) -> BundleSource:
    """BundleSource mock with an output schema."""
    import json

    source = _make_source(prompt)
    source.read_output_schema.return_value = OutputSchemaInfo(
        schema=schema, relative_path="output_schema.json"
    )
    source.bundle_files.return_value = {
        "system": prompt,
        "output_schema.json": json.dumps(schema),
    }
    return source


# ── Phase 1: inline_to_composition ────────────────────────────────────────────


class TestInlineToComposition:
    """Verify inline_to_composition behaviour."""

    def test_adds_default_composition_when_none(self) -> None:
        agent = _inline_agent("You are a helper.")
        result = inline_to_composition(agent)
        assert result.composition is not None
        assert isinstance(result.composition, CompositionConfig)

    def test_composition_has_all_defaults(self) -> None:
        agent = _inline_agent("You are a helper.")
        result = inline_to_composition(agent)
        assert result.composition is not None
        default = CompositionConfig()
        assert result.composition.system == default.system
        assert result.composition.references == default.references
        assert result.composition.user_template == default.user_template
        assert result.composition.input_schema == default.input_schema
        assert result.composition.output_schema == default.output_schema
        assert result.composition.transport == default.transport
        assert result.composition.output_validation == default.output_validation

    def test_no_op_when_composition_already_set(self) -> None:
        comp = CompositionConfig(output_validation="warn")
        agent = AgentDef(id="test-agent", prompt="p", composition=comp)
        result = inline_to_composition(agent)
        # Same object — no copy.
        assert result is agent
        assert result.composition is comp

    def test_prompt_preserved_on_copy(self) -> None:
        agent = _inline_agent("My system prompt.")
        result = inline_to_composition(agent)
        assert result.prompt == "My system prompt."
        assert result.id == "test-agent"

    def test_returns_different_object(self) -> None:
        agent = _inline_agent("prompt text")
        result = inline_to_composition(agent)
        # Must be a new object (copy) so callers are not mutating shared state.
        assert result is not agent

    def test_empty_prompt_synthesized(self) -> None:
        agent = _inline_agent("")
        result = inline_to_composition(agent)
        assert result.composition is not None

    def test_none_prompt_synthesized(self) -> None:
        agent = AgentDef(id="no-prompt", prompt=None, composition=None)
        result = inline_to_composition(agent)
        assert result.composition is not None


# ── Byte-identity: composed text == agent.prompt ──────────────────────────────


class TestByteIdentity:
    """Composed text from a synthesized-block agent equals agent.prompt."""

    def _composed_text(self, prompt: str, variables: dict | None = None) -> str:
        """Return PromptComposer().compose(source, variables).text for a source
        built from ``prompt``."""
        source = _make_source(prompt)
        return PromptComposer().compose(source, variables or {}).text

    def test_simple_prompt_byte_identical(self) -> None:
        prompt = "You are a helpful assistant.\n\nAnswer concisely."
        assert self._composed_text(prompt) == prompt

    def test_multiline_prompt_byte_identical(self) -> None:
        prompt = "Line 1\n\nLine 2\n\nLine 3"
        assert self._composed_text(prompt) == prompt

    def test_prompt_with_json_curly_braces_byte_identical(self) -> None:
        """JSON inside a prompt must not be treated as template variables."""
        prompt = 'Return: {"key": "value", "count": 1}'
        assert self._composed_text(prompt) == prompt

    def test_prompt_with_user_message_variable_substituted(self) -> None:
        """A prompt with {user_message} gets substituted when that variable is
        provided — this is the intended template behaviour for composition agents."""
        prompt = "You are an assistant. User said: {user_message}"
        variables = {"user_message": "hello"}
        composed = self._composed_text(prompt, variables)
        assert composed == "You are an assistant. User said: hello"

    def test_prompt_without_template_vars_unchanged_with_variables(self) -> None:
        """Variables dict does not alter a prompt with no {var} placeholders."""
        prompt = "You are a helper."
        variables = {"user_message": "some input"}
        assert self._composed_text(prompt, variables) == prompt

    def test_empty_prompt_byte_identical(self) -> None:
        assert self._composed_text("") == ""

    def test_prompt_with_output_schema_byte_identical_to_append_schema(self) -> None:
        """Output schema block is appended by PromptComposer, same as Stage 3 in build.py."""
        from agentbox.core.agents.composition.rendering import append_schema

        prompt = "You are an assistant."
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }
        source = _make_source_with_output_schema(prompt, schema)
        composed_text = PromptComposer().compose(source, {}).text
        expected = append_schema(prompt, schema)
        assert composed_text == expected
