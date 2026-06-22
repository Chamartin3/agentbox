"""Unit tests for cli/_context.py DI wiring."""

from __future__ import annotations

from pathlib import Path

from agentbox.cli.shared import build_ctx, get_settings, get_store


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
