"""Tests for render.py — materialize_rendered_config, cleanup, executor _render_for_run."""

from __future__ import annotations

from pathlib import Path

import pytest


def _settings(tmp_path):
    from agentbox.config import Settings

    return Settings(
        manifest_path=tmp_path / "manifest.toml",
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        port=0,
        host="127.0.0.1",
        agents_dir=None,
        agents_bundle_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
    )


def _executor(tmp_path):
    from agentbox.core.data import SessionStore
    from agentbox.core.deprecated.definitions import DefinitionLoader
    from agentbox.core.run.executor import RunExecutor

    settings = _settings(tmp_path)
    store = SessionStore(settings.db_path)
    loader = DefinitionLoader(settings.project_root)
    return RunExecutor(store, settings, loader)


def test_materialize_rendered_config_writes_files(tmp_path: Path) -> None:
    from agentbox.core.run.backends.base import RenderedConfig
    from agentbox.core.run.render import materialize_rendered_config

    run_dir = tmp_path / "run-files"
    rendered = RenderedConfig(
        files={
            Path("sub/config.json"): b'{"key": "value"}',
            Path("README.md"): b"# Hello",
        },
    )
    materialize_rendered_config(rendered, run_dir)

    assert (run_dir / "sub" / "config.json").read_bytes() == b'{"key": "value"}'
    assert (run_dir / "README.md").read_bytes() == b"# Hello"


def test_materialize_rendered_config_empty_files(tmp_path: Path) -> None:
    from agentbox.core.run.backends.base import RenderedConfig
    from agentbox.core.run.render import materialize_rendered_config

    run_dir = tmp_path / "run-empty"
    rendered = RenderedConfig(files={})
    materialize_rendered_config(rendered, run_dir)
    assert run_dir.is_dir()
    assert list(run_dir.iterdir()) == []


def test_materialize_rendered_config_sets_file_permissions(tmp_path: Path) -> None:
    from agentbox.core.run.backends.base import RenderedConfig
    from agentbox.core.run.render import materialize_rendered_config

    run_dir = tmp_path / "run-perm"
    rendered = RenderedConfig(
        files={Path("secret.txt"): b"data"},
    )
    materialize_rendered_config(rendered, run_dir)
    mode = (run_dir / "secret.txt").stat().st_mode
    assert mode & 0o777 == 0o600


def test_materialize_rendered_config_existing_dir_raises(tmp_path: Path) -> None:
    from agentbox.core.run.backends.base import RenderedConfig
    from agentbox.core.run.render import RunDirExists, materialize_rendered_config

    run_dir = tmp_path / "run-collision"
    run_dir.mkdir()  # pre-exist

    with pytest.raises(RunDirExists):
        materialize_rendered_config(RenderedConfig(files={}), run_dir)


def test_materialize_rendered_config_parent_dirs_auto_created(tmp_path: Path) -> None:
    from agentbox.core.run.backends.base import RenderedConfig
    from agentbox.core.run.render import materialize_rendered_config

    run_dir = tmp_path / "deep" / "nested" / "run-xyz"
    rendered = RenderedConfig(files={Path("a/b/c.json"): b"data"})
    materialize_rendered_config(rendered, run_dir)
    assert (run_dir / "a" / "b" / "c.json").read_bytes() == b"data"


def test_cleanup_run_dir_removes_directory(tmp_path: Path) -> None:
    from agentbox.core.run.executor import RunExecutor

    run_dir = tmp_path / "run-abc"
    run_dir.mkdir()
    (run_dir / "config.json").write_text("data")

    RunExecutor._cleanup_run_dir(run_dir)
    assert not run_dir.exists()


def test_cleanup_run_dir_skips_when_env_set(tmp_path: Path, monkeypatch) -> None:
    from agentbox.core.run.executor import RunExecutor

    monkeypatch.setenv("AGENTBOX_KEEP_RUN_DIRS", "1")
    run_dir = tmp_path / "run-abc"
    run_dir.mkdir()
    (run_dir / "config.json").write_text("data")

    RunExecutor._cleanup_run_dir(run_dir)
    assert run_dir.exists()


def test_cleanup_run_dir_none_no_error() -> None:
    from agentbox.core.run.executor import RunExecutor

    RunExecutor._cleanup_run_dir(None)


def test_render_for_run_creates_run_dir_and_generates_configs(
    tmp_path: Path, monkeypatch
) -> None:
    from agentbox.core.data.manifest import AgentDef, RunnerSpec
    from agentbox.core.run.backends.claude_code import ClaudeCodeBackend

    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    executor = _executor(tmp_path)

    agent = AgentDef(id="t", runner=RunnerSpec(kind="claude_code"))
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    adapter = ClaudeCodeBackend()
    rendered = adapter.render(agent, workdir)

    new_rendered, run_dir = executor._render_for_run(adapter, agent, workdir, rendered)

    assert run_dir.exists()
    assert run_dir.stat().st_mode & 0o700 == 0o700

    assert (run_dir / "claude_agents.json").exists()
    assert (run_dir / "claude_settings.json").exists()
    assert (run_dir / "claude_mcp.json").exists()
    assert (run_dir / "opencode.json").exists()

    assert new_rendered.cwd == run_dir
    assert new_rendered.digest != rendered.digest


def test_render_for_run_copies_claude_md(tmp_path: Path) -> None:
    from agentbox.core.data.manifest import AgentDef, RunnerSpec
    from agentbox.core.run.backends.claude_code import ClaudeCodeBackend

    executor = _executor(tmp_path)

    agent = AgentDef(id="t", runner=RunnerSpec(kind="claude_code"))
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "CLAUDE.md").write_text("# Agent instructions")

    adapter = ClaudeCodeBackend()
    rendered = adapter.render(agent, workdir)

    _, run_dir = executor._render_for_run(adapter, agent, workdir, rendered)

    assert (run_dir / "CLAUDE.md").exists()
    assert (run_dir / "CLAUDE.md").read_text() == "# Agent instructions"


def test_runs_tmpfs_dir_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = settings.runs_tmpfs_dir
    assert isinstance(result, Path)


def test_backend_includes_claude_md_in_files(tmp_path: Path) -> None:
    from agentbox.core.data.manifest import AgentDef, RunnerSpec
    from agentbox.core.run.backends.claude_code import ClaudeCodeBackend
    from agentbox.core.run.backends.opencode import OpenCodeBackend

    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "CLAUDE.md").write_text("# Guidance")

    agent = AgentDef(id="t", runner=RunnerSpec(kind="claude_code"))

    cc = ClaudeCodeBackend()
    rendered = cc.render(agent, workdir)
    assert Path("CLAUDE.md") in rendered.files
    assert rendered.files[Path("CLAUDE.md")] == b"# Guidance"

    oc = OpenCodeBackend()
    rendered = oc.render(agent, workdir)
    assert Path("CLAUDE.md") in rendered.files


def test_backend_cwd_is_relative(tmp_path: Path) -> None:
    from agentbox.core.data.manifest import AgentDef, RunnerSpec
    from agentbox.core.run.backends.claude_code import ClaudeCodeBackend
    from agentbox.core.run.backends.opencode import OpenCodeBackend
    from agentbox.core.run.backends.token import TokenBackend

    agent = AgentDef(id="t", runner=RunnerSpec(kind="claude_code"))
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    for backend_cls in (ClaudeCodeBackend, OpenCodeBackend, TokenBackend):
        adapter = backend_cls()
        rendered = adapter.render(agent, workdir)
        assert rendered.cwd == Path("."), f"{backend_cls.__name__} cwd is not relative"
