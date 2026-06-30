"""Unit tests for cli/shared/context.py DI wiring."""

from __future__ import annotations

from pathlib import Path

from agentbox.cli.shared import (
    AgentRenderer,
    EngineRenderer,
    OpsRenderer,
    Renderers,
    RunRenderer,
    SystemRenderer,
    WorkspaceRenderer,
    build_ctx,
)
from agentbox.cli.shared.deps import (
    get_agent_service,
    get_engine_service,
    get_evaluation_service,
    get_execution_service,
    get_settings,
    get_store,
    get_system_service,
)
from agentbox.core.service import AgentService, ExecutionService, EvaluationService, SystemService
from agentbox.core.service.engines.service import EngineService


def test_build_ctx_store_is_singleton(tmp_path: Path, monkeypatch) -> None:
    """DI wiring smoke check: build_ctx().store is the same lru_cache instance."""
    # Patch settings to use a temp directory
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("project = 'test'\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")

    # Clear caches so settings are re-read
    get_settings.cache_clear()
    get_store.cache_clear()

    ctx = build_ctx()
    assert ctx.store is get_store()

    get_settings.cache_clear()
    get_store.cache_clear()


def test_build_ctx_service_fields(tmp_path: Path, monkeypatch) -> None:
    """build_ctx() populates the five service fields with correct types."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("project = 'test'\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")

    # Clear all relevant caches
    for fn in (
        get_settings,
        get_store,
        get_agent_service,
        get_execution_service,
        get_engine_service,
        get_evaluation_service,
        get_system_service,
    ):
        fn.cache_clear()

    ctx = build_ctx()

    assert isinstance(ctx.agents, AgentService), f"Expected AgentService, got {type(ctx.agents)}"
    assert isinstance(ctx.execution, ExecutionService), f"Expected ExecutionService, got {type(ctx.execution)}"
    assert isinstance(ctx.engines, EngineService), f"Expected EngineService, got {type(ctx.engines)}"
    assert isinstance(ctx.evaluation, EvaluationService), f"Expected EvaluationService, got {type(ctx.evaluation)}"
    assert isinstance(ctx.system, SystemService), f"Expected SystemService, got {type(ctx.system)}"

    # Service instances are lru_cache singletons
    assert ctx.agents is get_agent_service()
    assert ctx.execution is get_execution_service()
    assert ctx.engines is get_engine_service()
    assert ctx.evaluation is get_evaluation_service()
    assert ctx.system is get_system_service()

    for fn in (
        get_settings,
        get_store,
        get_agent_service,
        get_execution_service,
        get_engine_service,
        get_evaluation_service,
        get_system_service,
    ):
        fn.cache_clear()


def test_build_ctx_render_registry(tmp_path: Path, monkeypatch) -> None:
    """build_ctx() populates render as a Renderers registry with six typed components."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("project = 'test'\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")

    for fn in (get_settings, get_store):
        fn.cache_clear()

    ctx = build_ctx()

    assert isinstance(ctx.render, Renderers), f"Expected Renderers, got {type(ctx.render)}"
    assert isinstance(ctx.render.agent, AgentRenderer), f"Expected AgentRenderer, got {type(ctx.render.agent)}"
    assert isinstance(ctx.render.engine, EngineRenderer), f"Expected EngineRenderer, got {type(ctx.render.engine)}"
    assert isinstance(ctx.render.run, RunRenderer), f"Expected RunRenderer, got {type(ctx.render.run)}"
    assert isinstance(ctx.render.workspace, WorkspaceRenderer), f"Expected WorkspaceRenderer, got {type(ctx.render.workspace)}"
    assert isinstance(ctx.render.system, SystemRenderer), f"Expected SystemRenderer, got {type(ctx.render.system)}"
    assert isinstance(ctx.render.ops, OpsRenderer), f"Expected OpsRenderer, got {type(ctx.render.ops)}"

    for fn in (get_settings, get_store):
        fn.cache_clear()
