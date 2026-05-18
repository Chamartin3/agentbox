"""Tests for ManifestWriter composition serialization with shared refs.

Tests that:
- SharedRef instances and dicts with 'shared' key are serialized as inline tables
- Version pins are included when present
- String paths are preserved as-is
- Mixed lists (strings + shared refs) work correctly
- Round-trip through loader works
- All three formats (markdown, standalone_toml, legacy_dir) are supported
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit
from agentbox.core.data.manifest import (
    AgentDef,
    AgentSource,
    CompositionConfig,
    SharedRef,
)
from agentbox.core.deprecated.definitions import DefinitionLoader, ManifestWriter


@pytest.fixture
def tmp_agent_project(tmp_path: Path) -> Path:
    """Create a minimal agentbox project structure."""
    (tmp_path / "agents.d").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_writer_serializes_shared_ref_dict_form(tmp_agent_project: Path) -> None:
    """AgentDef with Composition(system={"shared": "x"}) → write → read back → composition.system is SharedRef."""
    agent = AgentDef(
        id="test_agent",
        composition=CompositionConfig(system={"shared": "schema/job-eval"}),
    )
    agent.source_format = AgentSource.STANDALONE_TOML
    agent.source_path = tmp_agent_project / "agents.d" / "test_agent.toml"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    # Read back via loader
    loader = DefinitionLoader(tmp_agent_project)
    loaded = loader.get("test_agent")

    assert loaded is not None
    assert loaded.composition is not None
    # Loader normalizes dicts to SharedRef objects
    assert isinstance(loaded.composition.system, SharedRef)
    assert loaded.composition.system.shared == "schema/job-eval"
    assert loaded.composition.system.version is None


def test_writer_serializes_shared_ref_with_version(tmp_agent_project: Path) -> None:
    """AgentDef with versioned SharedRef → write → read back preserves version."""
    agent = AgentDef(
        id="versioned_agent",
        composition=CompositionConfig(
            system={"shared": "schema/job-eval-v3", "version": 3}
        ),
    )
    agent.source_format = AgentSource.STANDALONE_TOML
    agent.source_path = tmp_agent_project / "agents.d" / "versioned_agent.toml"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    # Read back
    loader = DefinitionLoader(tmp_agent_project)
    loaded = loader.get("versioned_agent")

    assert loaded is not None
    assert loaded.composition is not None
    # Loader normalizes to SharedRef
    assert isinstance(loaded.composition.system, SharedRef)
    assert loaded.composition.system.shared == "schema/job-eval-v3"
    assert loaded.composition.system.version == 3


def test_writer_serializes_mixed_list(tmp_agent_project: Path) -> None:
    """references: ["path/to/file.md", {"shared": "y"}] → write → read → both preserved."""
    agent = AgentDef(
        id="mixed_refs_agent",
        composition=CompositionConfig(
            system="prompts/system.md",
            references=["README.md", {"shared": "guidelines/writing"}],
        ),
    )
    agent.source_format = AgentSource.STANDALONE_TOML
    agent.source_path = tmp_agent_project / "agents.d" / "mixed_agent.toml"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    # Verify the written TOML contains the inline table
    toml_text = agent.source_path.read_text(encoding="utf-8")
    assert "README.md" in toml_text
    assert 'shared = "guidelines/writing"' in toml_text

    # Read back
    loader = DefinitionLoader(tmp_agent_project)
    loaded = loader.get("mixed_refs_agent")

    assert loaded is not None
    assert loaded.composition is not None
    assert len(loaded.composition.references) == 2
    assert loaded.composition.references[0] == "README.md"
    # Second one is the shared ref (as dict or SharedRef depending on Pydantic's handling)
    ref2 = loaded.composition.references[1]
    if isinstance(ref2, dict):
        assert ref2.get("shared") == "guidelines/writing"
    else:
        assert isinstance(ref2, SharedRef)
        assert ref2.shared == "guidelines/writing"


def test_writer_preserves_string_paths(tmp_agent_project: Path) -> None:
    """Regression: plain strings still serialize as strings, not broken."""
    agent = AgentDef(
        id="string_paths_agent",
        composition=CompositionConfig(
            system="prompts/system.md",
            references=["docs/README.md", "docs/guidelines.md"],
            user_template="prompts/user.md",
        ),
    )
    agent.source_format = AgentSource.STANDALONE_TOML
    agent.source_path = tmp_agent_project / "agents.d" / "strings_agent.toml"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    # Verify TOML syntax is correct (no inline tables)
    toml_text = agent.source_path.read_text(encoding="utf-8")
    doc = tomlkit.parse(toml_text)
    assert doc["composition"]["system"] == "prompts/system.md"
    assert len(doc["composition"]["references"]) == 2
    assert doc["composition"]["references"][0] == "docs/README.md"

    # Read back
    loader = DefinitionLoader(tmp_agent_project)
    loaded = loader.get("string_paths_agent")

    assert loaded is not None
    assert loaded.composition is not None
    assert loaded.composition.system == "prompts/system.md"
    assert loaded.composition.references == ["docs/README.md", "docs/guidelines.md"]
    assert loaded.composition.user_template == "prompts/user.md"


def test_writer_markdown_format_with_shared_refs(tmp_agent_project: Path) -> None:
    """Markdown format with composition containing shared refs → write → read."""
    agent = AgentDef(
        id="markdown_agent",
        description="A markdown-defined agent",
        prompt="# System Prompt\nYou are helpful.",
        composition=CompositionConfig(
            system={"shared": "schema/eval-v2", "version": 2},
            output_schema={"shared": "schema/output"},
        ),
    )
    agent.source_format = AgentSource.MARKDOWN
    agent.source_path = tmp_agent_project / "agents.d" / "markdown_agent.md"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    # Verify file was created
    assert agent.source_path.exists()
    md_text = agent.source_path.read_text(encoding="utf-8")
    # YAML should contain composition with shared ref
    assert "shared: schema/eval-v2" in md_text or "shared: 'schema/eval-v2'" in md_text
    assert "version: 2" in md_text

    # Read back
    loader = DefinitionLoader(tmp_agent_project)
    loaded = loader.get("markdown_agent")

    assert loaded is not None
    assert loaded.composition is not None
    assert loaded.composition.output_schema is not None


def test_writer_legacy_dir_format_with_shared_refs(tmp_agent_project: Path) -> None:
    """Legacy dir format with composition → write → read."""
    agent = AgentDef(
        id="legacy_agent",
        composition=CompositionConfig(
            system={"shared": "prompts/system-v1"},
            references=["docs/guidelines.md", {"shared": "resources/faq"}],
        ),
    )
    agent.source_format = AgentSource.LEGACY_DIR
    agent.source_path = tmp_agent_project / "agents" / "legacy_agent"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    # Verify agent.toml exists and contains composition
    agent_toml = tmp_agent_project / "agents" / "legacy_agent" / "agent.toml"
    assert agent_toml.exists()
    toml_text = agent_toml.read_text(encoding="utf-8")
    assert "[composition]" in toml_text
    assert 'shared = "prompts/system-v1"' in toml_text

    # Read back
    loader = DefinitionLoader(tmp_agent_project)
    loaded = loader.get("legacy_agent")

    assert loaded is not None
    assert loaded.composition is not None


def test_writer_inline_toml_with_shared_refs(tmp_agent_project: Path) -> None:
    """Inline agent in agentbox.toml with composition → write → read."""
    # Create a manifest with an inline agent
    manifest_text = """\
[[agents]]
id = "inline_agent"
description = "An inline agent"

[agents.composition]
system = { shared = "schema/system" }

[agents.runner]
model = "haiku"
"""
    manifest_path = tmp_agent_project / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    # Read the agent
    loader = DefinitionLoader(tmp_agent_project)
    agent = loader.get("inline_agent")

    assert agent is not None
    assert agent.composition is not None
    assert agent.source_format == AgentSource.INLINE_TOML

    # Now save it back via ManifestWriter
    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    # Verify it can be re-loaded
    loader2 = DefinitionLoader(tmp_agent_project)
    reloaded = loader2.get("inline_agent")

    assert reloaded is not None
    assert reloaded.composition is not None


def test_composition_table_only_when_set(tmp_agent_project: Path) -> None:
    """Agent without composition should not emit [composition] section."""
    agent = AgentDef(
        id="no_composition",
        prompt_path="prompts/system.md",
    )
    agent.source_format = AgentSource.STANDALONE_TOML
    agent.source_path = tmp_agent_project / "agents.d" / "no_comp.toml"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    toml_text = agent.source_path.read_text(encoding="utf-8")
    assert "[composition]" not in toml_text
    assert 'prompt_path = "prompts/system.md"' in toml_text


def test_composition_with_all_fields(tmp_agent_project: Path) -> None:
    """Composition with all optional fields populated → write → read."""
    agent = AgentDef(
        id="full_composition",
        composition=CompositionConfig(
            system={"shared": "system-v1"},
            references=["doc1.md", {"shared": "doc2"}],
            user_template={"shared": "templates/user"},
            input_schema={"shared": "schemas/input"},
            output_schema={"shared": "schemas/output", "version": 2},
            transport="file",
            output_validation="warn",
        ),
    )
    agent.source_format = AgentSource.STANDALONE_TOML
    agent.source_path = tmp_agent_project / "agents.d" / "full.toml"

    writer = ManifestWriter(tmp_agent_project)
    writer.save_agent(agent)

    toml_text = agent.source_path.read_text(encoding="utf-8")
    doc = tomlkit.parse(toml_text)
    comp = doc["composition"]

    assert comp["system"]["shared"] == "system-v1"
    assert comp["transport"] == "file"
    assert comp["output_validation"] == "warn"
    assert len(comp["references"]) == 2

    # Read back
    loader = DefinitionLoader(tmp_agent_project)
    loaded = loader.get("full_composition")

    assert loaded is not None
    assert loaded.composition is not None
    assert loaded.composition.transport == "file"
    assert loaded.composition.output_validation == "warn"
