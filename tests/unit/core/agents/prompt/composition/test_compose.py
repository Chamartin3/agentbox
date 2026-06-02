"""Unit tests for agentbox.core.agents.prompt.composition.compose()."""

from pathlib import Path

import pytest
from agentbox.core.agents.prompt.composition import ComposeResult, compose


def _write_bundle(tmp_path: Path, agent_toml: str, files: dict[str, str]) -> Path:
    bundle = tmp_path / "test_bundle"
    bundle.mkdir()
    (bundle / "agent.toml").write_text(agent_toml, encoding="utf-8")
    for rel_path, content in files.items():
        full = bundle / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return bundle


class TestCompose:
    def test_compose_minimal(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"
""",
            files={
                "prompts/system.md": "Hello {name}",
            },
        )
        result = compose(bundle, {"name": "World"}, {})
        assert isinstance(result, ComposeResult)
        assert result.system == "Hello World"
        assert result.user == ""
        assert result.schema is None
        assert result.bundle_sha

    def test_compose_with_user_template(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"
user_template = "prompts/user.md"
""",
            files={
                "prompts/system.md": "System {x}",
                "prompts/user.md": "User {y}",
            },
        )
        result = compose(bundle, {"x": "A", "y": "B"}, {})
        assert result.system == "System A"
        assert result.user == "User B"

    def test_compose_fallback_user_message(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"
""",
            files={
                "prompts/system.md": "System",
            },
        )
        result = compose(bundle, {"user_message": "hello"}, {})
        assert result.user == "hello"

    def test_compose_with_shared_references(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "rules.md").write_text("Rule 1", encoding="utf-8")

        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"

[[composition.references]]
path = "shared://drafting/rules.md"
heading = "Rules"
""",
            files={
                "prompts/system.md": "System",
            },
        )
        result = compose(bundle, {}, {"drafting": shared})
        assert "## Rules\n\nRule 1" in result.system

    def test_compose_reference_heading_defaults_to_stem(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "my_guide.md").write_text("Content", encoding="utf-8")

        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"

[[composition.references]]
path = "shared://drafting/my_guide.md"
""",
            files={
                "prompts/system.md": "System",
            },
        )
        result = compose(bundle, {}, {"drafting": shared})
        assert "## my_guide\n\nContent" in result.system

    def test_compose_missing_variable_raises(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"
""",
            files={
                "prompts/system.md": "Hello {missing}",
            },
        )
        with pytest.raises(KeyError):
            compose(bundle, {}, {})

    def test_compose_missing_agent_toml_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compose(tmp_path / "nonexistent", {}, {})

    def test_compose_missing_system_prompt_raises(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"
""",
            files={},
        )
        with pytest.raises(FileNotFoundError):
            compose(bundle, {}, {})

    def test_compose_unknown_shared_root_raises(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"

[[composition.references]]
path = "shared://unknown/file.md"
""",
            files={"prompts/system.md": "System"},
        )
        with pytest.raises(ValueError, match="Unknown shared root"):
            compose(bundle, {}, {})

    def test_compose_output_schema(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"
output_schema = "output_schema.json"
""",
            files={
                "prompts/system.md": "System",
                "output_schema.json": '{"type": "object"}',
            },
        )
        result = compose(bundle, {}, {})
        assert result.schema == {"type": "object"}
        assert result.schema_sha is not None

    def test_compose_bundle_sha_stable(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
[composition]
system_prompt = "prompts/system.md"
""",
            files={
                "prompts/system.md": "Stable",
            },
        )
        r1 = compose(bundle, {}, {})
        r2 = compose(bundle, {}, {})
        assert r1.bundle_sha == r2.bundle_sha

    def test_compose_missing_composition_block_raises(self, tmp_path: Path) -> None:
        bundle = _write_bundle(
            tmp_path,
            agent_toml="""
id = "test"
""",
            files={},
        )
        with pytest.raises(ValueError, match=r"missing \[composition\] block"):
            compose(bundle, {}, {})
