"""Executor backend selection tests — explicit backend, preference list,
fallback to kind, unsupported_backends, NO_BACKEND_AVAILABLE."""

from __future__ import annotations

from pathlib import Path

from agentbox.config import Settings
from agentbox.core.constants import RunnerKind
from agentbox.core.data import SessionStore
from agentbox.core.data.manifest import AgentDef, RunnerSpec
from agentbox.core.definitions import DefinitionLoader
from agentbox.core.executor import RunExecutor


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        manifest_path=tmp_path / "manifest.toml",
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        port=0,
        host="127.0.0.1",
        agents_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
    )


def test_explicit_backend_is_honored(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = SessionStore(settings.db_path)
    loader = DefinitionLoader(settings.project_root)
    executor = RunExecutor(store, settings, loader)

    agent = AgentDef(
        id="test",
        runner=RunnerSpec(kind=RunnerKind.PYDANTIC_AI),
    )
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    adapter, rendered = executor._select_backend(
        agent, workdir, backend_override="claude_code"
    )
    assert adapter.name == "claude_code"
    assert rendered.cwd == Path(".")


def test_missing_backend_raises(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = SessionStore(settings.db_path)
    loader = DefinitionLoader(settings.project_root)
    executor = RunExecutor(store, settings, loader)

    agent = AgentDef(
        id="test",
        runner=RunnerSpec(kind=RunnerKind.PYDANTIC_AI),
    )
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    import pytest

    with pytest.raises(KeyError, match="NO_BACKEND_AVAILABLE"):
        executor._select_backend(agent, workdir, backend_override="nonexistent_backend")


def test_fallback_to_kind_when_no_preference(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = SessionStore(settings.db_path)
    loader = DefinitionLoader(settings.project_root)
    executor = RunExecutor(store, settings, loader)

    agent = AgentDef(
        id="test",
        runner=RunnerSpec(kind=RunnerKind.CLAUDE_CODE),
    )
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    adapter, _rendered = executor._select_backend(agent, workdir)
    assert adapter.name == "claude_code"


def test_unsupported_backends_skipped_in_preference(tmp_path: Path) -> None:
    """When backend_preference contains an unsupported backend, skip it."""
    settings = _make_settings(tmp_path)
    store = SessionStore(settings.db_path)
    loader = DefinitionLoader(settings.project_root)
    executor = RunExecutor(store, settings, loader)

    agent = AgentDef(
        id="test",
        runner=RunnerSpec(kind=RunnerKind.CLAUDE_CODE),
        unsupported_backends=["claude_code", "opencode", "pydantic_ai"],
    )
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)

    # Write a manifest with backend_preference
    toml_path = settings.project_root / "agentbox.toml"
    toml_path.write_text(
        'project = "test"\n'
        'backend_preference = ["claude_code", "opencode", "pydantic_ai"]\n'
    )

    # The executor caches the loader result; create a new one.
    import pytest

    with pytest.raises(KeyError, match="NO_BACKEND_AVAILABLE"):
        executor._select_backend(agent, workdir)
