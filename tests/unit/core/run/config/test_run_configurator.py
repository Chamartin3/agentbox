"""Tests for RunConfigurator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.engines.render.backends import get_generator, list_generators
from agentbox.core.engines.render.run_configurator import (
    ComposedMetadata,
    RunConfigurator,
)
from agentbox.core.engines.render.skills.filter import filter_skills_for_backend


def _make_agent(**overrides: object) -> AgentDef:
    kwargs = {
        "id": "test.agent",
        "runner": RunnerSpec(),
        "description": "A test agent",
    }
    kwargs.update(overrides)
    return AgentDef(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def tmp_runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def composed() -> ComposedMetadata:
    return ComposedMetadata(
        system="## System\nDo the thing.",
        user='{"job_id": 42}',
        schema={"type": "object"},
        bundle_sha="abc123",
        variables={"x": "1"},
    )


# ---------------------------------------------------------------------------
# Cache key tests
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_cache_key_is_stable(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        key1 = cfg._compute_cache_key(agent, "opencode", composed)
        key2 = cfg._compute_cache_key(agent, "opencode", composed)
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex

    def test_cache_key_changes_with_agent_id(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        a1 = _make_agent(id="agent.a")
        a2 = _make_agent(id="agent.b")
        k1 = cfg._compute_cache_key(a1, "opencode", composed)
        k2 = cfg._compute_cache_key(a2, "opencode", composed)
        assert k1 != k2

    def test_cache_key_changes_with_backend(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        k1 = cfg._compute_cache_key(agent, "opencode", composed)
        k2 = cfg._compute_cache_key(agent, "claude_code", composed)
        assert k1 != k2


# ---------------------------------------------------------------------------
# prepare_run_dir — fresh generation
# ---------------------------------------------------------------------------


class TestPrepareRunDirFresh:
    def test_creates_prompts(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )

        assert run_cfg.is_fresh
        assert (run_cfg.prompt_dir / "system.md").exists()
        assert (run_cfg.prompt_dir / "user.md").exists()
        assert (run_cfg.prompt_dir / "schema.json").exists()

        system_text = (run_cfg.prompt_dir / "system.md").read_text()
        assert "Do the thing." in system_text

    def test_creates_backend_dir(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        assert run_cfg.backend_dir.exists()

    def test_creates_meta(self, tmp_runs_dir: Path, composed: ComposedMetadata) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        meta = run_cfg.meta
        assert meta["agent_id"] == "test.agent"
        assert meta["backend"] == "opencode"
        assert "cache_key" in meta
        assert "created_at" in meta

    def test_creates_opencode_markdown_agent(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        md_path = run_cfg.backend_dir / "agents" / "test.agent.md"
        assert md_path.exists()
        content = md_path.read_text()
        assert "---" in content
        assert "System Instructions" in content
        assert "Task Input" in content

    def test_creates_claude_markdown_agent(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="claude_code",
            composed=composed,
        )
        md_path = run_cfg.backend_dir / "agents" / "test.agent.md"
        assert md_path.exists()
        content = md_path.read_text()
        assert "---" in content
        assert "name: test.agent" in content
        assert "System Instructions" in content


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class TestCaching:
    def test_cache_hit_reuses_directory(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        r1 = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        r2 = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        assert r1.run_dir == r2.run_dir
        assert r2.is_fresh is False

    def test_force_regenerates(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        r1 = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        r2 = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
            force=True,
        )
        assert r1.run_dir != r2.run_dir
        assert r2.is_fresh is True

    def test_stale_cache_is_ignored(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(
            Path("/tmp"),
            runs_tmpfs_dir=tmp_runs_dir,
            max_cache_age_seconds=0,  # immediately stale
        )
        cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        # Because max_cache_age is 0, the next call should see it as stale
        # and create a new one (or reuse after regeneration)
        # Actually with 0 seconds, even the freshly created one is stale,
        # so the second call should create a new one.
        r2 = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        # Since the first one is stale, it should create a new one
        assert r2.is_fresh is True


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestSkills:
    def test_copies_skills_for_opencode(
        self, tmp_runs_dir: Path, composed: ComposedMetadata, tmp_path: Path
    ) -> None:
        # Seed a workspace with a skill
        ws = tmp_path / "workspace"
        skill_dir = ws / ".opencode" / "skills" / "resume-writing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: resume-writing\n---\n\n# Resume Writing\n", encoding="utf-8"
        )

        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        run_cfg = cfg.prepare_run_dir(
            workdir=ws,
            agent=agent,
            backend="opencode",
            composed=composed,
        )
        copied_skill = run_cfg.backend_dir / "skills" / "resume-writing" / "SKILL.md"
        assert copied_skill.exists()
        assert "Resume Writing" in copied_skill.read_text()

    def test_copies_skills_for_claude(
        self, tmp_runs_dir: Path, composed: ComposedMetadata, tmp_path: Path
    ) -> None:
        ws = tmp_path / "workspace"
        skill_dir = ws / ".claude" / "skills" / "resume-writing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: resume-writing\n---\n\n# Resume Writing\n", encoding="utf-8"
        )

        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        run_cfg = cfg.prepare_run_dir(
            workdir=ws,
            agent=agent,
            backend="claude_code",
            composed=composed,
        )
        copied_skill = run_cfg.backend_dir / "skills" / "resume-writing" / "SKILL.md"
        assert copied_skill.exists()


# ---------------------------------------------------------------------------
# Skill filtering
# ---------------------------------------------------------------------------


class TestSkillFilter:
    def test_no_runners_means_all_backends(self) -> None:
        from agentbox.core.resource.skills import SkillPack

        skill = SkillPack(
            name="generic",
            path=Path("/tmp/skills/generic"),
            content="---\nname: generic\n---\n\n# Generic\n",
        )
        assert filter_skills_for_backend([skill], "opencode") == [skill]
        assert filter_skills_for_backend([skill], "claude_code") == [skill]

    def test_runners_field_filters(self) -> None:
        from agentbox.core.resource.skills import SkillPack

        opencode_only = SkillPack(
            name="oc",
            path=Path("/tmp/skills/oc"),
            content="---\nrunners: [opencode]\n---\n\n# OC\n",
        )
        claude_only = SkillPack(
            name="cc",
            path=Path("/tmp/skills/cc"),
            content="---\nrunners: [claude_code]\n---\n\n# CC\n",
        )
        assert filter_skills_for_backend([opencode_only, claude_only], "opencode") == [
            opencode_only
        ]
        assert filter_skills_for_backend(
            [opencode_only, claude_only], "claude_code"
        ) == [claude_only]

    def test_multiple_backends_in_runners(self) -> None:
        from agentbox.core.resource.skills import SkillPack

        shared = SkillPack(
            name="shared",
            path=Path("/tmp/skills/shared"),
            content="---\nrunners: [opencode, claude_code]\n---\n\n# Shared\n",
        )
        assert filter_skills_for_backend([shared], "opencode") == [shared]
        assert filter_skills_for_backend([shared], "claude_code") == [shared]


# ---------------------------------------------------------------------------
# Generator registry
# ---------------------------------------------------------------------------


class TestGeneratorRegistry:
    def test_all_backends_registered(self) -> None:
        assert set(list_generators()) == {"opencode", "claude_code", "codex", "pi"}

    def test_get_generator_returns_instance(self) -> None:
        from agentbox.core.engines.render.backends.opencode import (
            OpenCodeConfigGenerator,
        )

        gen = get_generator("opencode")
        assert isinstance(gen, OpenCodeConfigGenerator)

    def test_get_generator_returns_none_for_unknown(self) -> None:
        assert get_generator("nonexistent") is None


class TestMcpConfig:
    def test_opencode_generates_mcp_config(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        from agentbox.core.engines.render.backends.base import McpConfig

        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        mcp = McpConfig(
            server_name="test-mcp", url="http://localhost:3000", transport="http"
        )
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
            mcp=mcp,
        )
        oc_json = run_cfg.backend_dir / "opencode.json"
        assert oc_json.exists()
        data = json.loads(oc_json.read_text())
        assert "mcp" in data
        assert "test-mcp" in data["mcp"]
        assert data["mcp"]["test-mcp"]["type"] == "remote"
        assert data["mcp"]["test-mcp"]["url"] == "http://localhost:3000"

    def test_claude_generates_mcp_config(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        from agentbox.core.engines.render.backends.base import McpConfig

        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        mcp = McpConfig(
            server_name="test-mcp",
            command=["python", "-m", "mcp_server"],
            transport="stdio",
        )
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="claude_code",
            composed=composed,
            mcp=mcp,
        )
        mcp_json = run_cfg.backend_dir / "claude_mcp.json"
        assert mcp_json.exists()
        data = json.loads(mcp_json.read_text())
        assert "mcpServers" in data
        assert "test-mcp" in data["mcpServers"]
        assert data["mcpServers"]["test-mcp"]["command"] == "python"
        assert data["mcpServers"]["test-mcp"]["args"] == ["-m", "mcp_server"]

    def test_generators_skip_mcp_when_none(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)

        # Claude without MCP should not write claude_mcp.json
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="claude_code",
            composed=composed,
            mcp=None,
        )
        assert not (run_cfg.backend_dir / "claude_mcp.json").exists()

    def test_opencode_mcp_local_mode(
        self, tmp_runs_dir: Path, composed: ComposedMetadata
    ) -> None:
        from agentbox.core.engines.render.backends.base import McpConfig

        agent = _make_agent()
        cfg = RunConfigurator(Path("/tmp"), runs_tmpfs_dir=tmp_runs_dir)
        mcp = McpConfig(command=["./mcp_serve.sh"])
        run_cfg = cfg.prepare_run_dir(
            workdir=Path("/tmp/workspace"),
            agent=agent,
            backend="opencode",
            composed=composed,
            mcp=mcp,
        )
        oc_json = run_cfg.backend_dir / "opencode.json"
        data = json.loads(oc_json.read_text())
        assert data["mcp"]["mcp"]["type"] == "local"
        assert data["mcp"]["mcp"]["command"] == ["./mcp_serve.sh"]
