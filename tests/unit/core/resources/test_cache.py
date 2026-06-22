"""Tests for resource blob cache (Plan 08 Phase 2)."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from threading import Thread

import pytest
from agentbox.core.config import load_settings
from agentbox.core.resources.cache import ensure_cached, prune_cache


def _blobs(names: list[str]) -> list[dict]:
    return [{"path": name, "content": f"content of {name}".encode()} for name in names]


class TestEnsureCached:
    def test_writes_blobs(self, tmp_path: Path):
        cache = tmp_path / "cache"
        result = ensure_cached("v1", _blobs(["a.txt", "sub/b.txt"]), cache)
        assert result == cache / "v1"
        assert (result / "a.txt").read_bytes() == b"content of a.txt"
        assert (result / "sub" / "b.txt").read_bytes() == b"content of sub/b.txt"

    def test_idempotent_on_existing_entry(self, tmp_path: Path):
        cache = tmp_path / "cache"
        ensure_cached("v1", _blobs(["a.txt"]), cache)
        # Overwrite the file to prove idempotent path doesn't re-write
        (cache / "v1" / "a.txt").write_bytes(b"tampered")
        result = ensure_cached("v1", _blobs(["a.txt"]), cache)
        assert (result / "a.txt").read_bytes() == b"tampered"

    def test_string_content_written_as_utf8(self, tmp_path: Path):
        cache = tmp_path / "cache"
        blobs = [{"path": "readme.md", "content": "hello 🌍"}]
        result = ensure_cached("v2", blobs, cache)
        assert (result / "readme.md").read_text(encoding="utf-8") == "hello 🌍"

    def test_no_partial_writes_on_exception(self, tmp_path: Path):
        cache = tmp_path / "cache"
        bad_blobs = [{"path": "", "content": b"bad"}]  # empty path causes error

        with pytest.raises((OSError, ValueError)):
            ensure_cached("vbad", bad_blobs, cache)
        # Either the dest doesn't exist or it's clean — no partial entry
        dest = cache / "vbad"
        assert not dest.exists()

    def test_concurrent_materialization_hits_cache_once(self, tmp_path: Path):
        """Two concurrent materializations produce one complete entry."""
        cache = tmp_path / "cache"
        blobs = _blobs(["file.txt"])
        results = []
        errors = []

        def _run():
            try:
                r = ensure_cached("v-concurrent", blobs, cache)
                results.append(r)
            except Exception as exc:
                errors.append(exc)

        t1, t2 = Thread(target=_run), Thread(target=_run)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"errors: {errors}"
        assert len(results) == 2
        # Both returned the same path
        assert results[0] == results[1]
        # Entry is complete
        assert (results[0] / "file.txt").exists()

    def test_cache_corruption_recovery(self, tmp_path: Path):
        """If the cached dir is deleted mid-run, next call re-materializes."""
        cache = tmp_path / "cache"
        ensure_cached("v1", _blobs(["a.txt"]), cache)
        # Simulate corruption: delete the cached blob
        (cache / "v1" / "a.txt").unlink()
        # ensure_cached won't re-write because the dir still exists (idempotent)
        # Caller must remove the dir to trigger re-materialization
        shutil.rmtree(cache / "v1")
        result = ensure_cached("v1", _blobs(["a.txt"]), cache)
        assert (result / "a.txt").exists()


class TestPruneCache:
    def test_prune_removes_old_entries(self, tmp_path: Path):
        cache = tmp_path / "cache"
        ensure_cached("v-old", _blobs(["f.txt"]), cache)
        # Manually backdate the directory's mtime
        old_time = time.time() - 35 * 86400
        os.utime(cache / "v-old", (old_time, old_time))

        removed = prune_cache(cache, older_than_days=30)
        assert removed == 1
        assert not (cache / "v-old").exists()

    def test_prune_keeps_recent_entries(self, tmp_path: Path):
        cache = tmp_path / "cache"
        ensure_cached("v-new", _blobs(["f.txt"]), cache)

        removed = prune_cache(cache, older_than_days=30)
        assert removed == 0
        assert (cache / "v-new").exists()

    def test_prune_nonexistent_cache_returns_zero(self, tmp_path: Path):
        assert prune_cache(tmp_path / "no-such-cache", older_than_days=30) == 0


class TestSettingsResourceCacheDir:
    def test_default_is_data_dir_resource_cache(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("AGENTBOX_RESOURCE_CACHE_DIR", raising=False)
        settings = load_settings()
        assert settings.resource_cache_dir == tmp_path / "resource_cache"

    def test_custom_cache_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        custom = tmp_path / "my_cache"
        monkeypatch.setenv("AGENTBOX_RESOURCE_CACHE_DIR", str(custom))
        settings = load_settings()
        assert settings.resource_cache_dir == custom
